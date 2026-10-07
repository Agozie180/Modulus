// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

/// @title WeekendOracle v2 - Modulus seals its Monday-open forecasts on BNB Chain before Wall Street wakes.
/// @notice commit() inside the dark weekend (Fri 20:00 UTC - Sun 22:00 UTC), reveal() from Monday 13:30 UTC
///         (US open during EDT; 14:30 UTC during EST), then anyone can prove a single forecast with a Merkle proof.
///         commitment = sha256(merkleRoot || salt)
///         leaf       = sha256(utf8("YYYY-MM-DD|TICKER|gap_hat_bps|p_up"))   (exactly modulus/oracle.py:leaf)
///         node       = sha256(min(a,b) || max(a,b))                          (sorted pairs, odd level duplicates last)
///         weekId     = the Friday as yyyymmdd (e.g. 20261009), exactly what `python -m modulus oracle commit` prints.
contract WeekendOracle {
    struct Week {
        bytes32 commitment;
        bytes32 root;
        uint40 committedAt;
        uint40 revealedAt;
        uint40 gradedAt;
        uint32 nForecasts;
        int32 hitBps;   // hit rate x 1e4  (0.7212 -> 7212)
        int32 brierBps; // Brier x 1e4     (0.2230 -> 2230)
    }

    uint256 private constant COMMIT_OPEN = 20 hours;                     // Fri 20:00 UTC
    uint256 private constant COMMIT_CLOSE = 2 days + 22 hours;           // Sun 22:00 UTC
    uint256 private constant REVEAL_OPEN = 3 days + 13 hours + 30 minutes; // Mon 13:30 UTC

    address public immutable agent;        // Modulus agent wallet (owner of its ERC-8004 identity)
    bool public immutable enforceWindow;   // true on mainnet; false lets you rehearse on testnet mid-week
    uint256 public erc8004AgentId;         // set once, links this oracle to the ERC-8004 identity
    bool public erc8004AgentIdSet;         // ERC-8004 ids start at 0, so 0 cannot mean "unset"
    mapping(uint64 => Week) public forecastWeeks; // NB: `weeks` is a reserved Solidity time unit and does not compile

    event Committed(uint64 indexed weekId, bytes32 commitment, uint256 nForecasts);
    event Revealed(uint64 indexed weekId, bytes32 root, bytes32 salt);
    event Graded(uint64 indexed weekId, int32 hitBps, int32 brierBps);
    event AgentIdSet(uint256 agentId);

    error NotAgent();
    error BadWeekId();
    error OutsideWindow();
    error BadState();
    error CommitmentMismatch();
    error BadScore();

    modifier onlyAgent() {
        if (msg.sender != agent) revert NotAgent();
        _;
    }

    constructor(bool enforceWindow_) {
        agent = msg.sender;
        enforceWindow = enforceWindow_;
    }

    function setErc8004AgentId(uint256 agentId) external onlyAgent {
        if (erc8004AgentIdSet) revert BadState();
        erc8004AgentIdSet = true;
        erc8004AgentId = agentId;
        emit AgentIdSet(agentId);
    }

    function commit(uint64 weekId, bytes32 commitment, uint32 nForecasts) external onlyAgent {
        uint256 fri = fridayStart(weekId); // validates the id and that it is a Friday
        if (enforceWindow && (block.timestamp < fri + COMMIT_OPEN || block.timestamp >= fri + COMMIT_CLOSE)) {
            revert OutsideWindow();
        }
        Week storage w = forecastWeeks[weekId];
        if (w.committedAt != 0 || commitment == bytes32(0)) revert BadState(); // no edits, ever
        w.commitment = commitment;
        w.nForecasts = nForecasts;
        w.committedAt = uint40(block.timestamp);
        emit Committed(weekId, commitment, nForecasts);
    }

    function reveal(uint64 weekId, bytes32 root, bytes32 salt) external onlyAgent {
        Week storage w = forecastWeeks[weekId];
        if (w.committedAt == 0 || w.revealedAt != 0) revert BadState();
        if (enforceWindow && block.timestamp < fridayStart(weekId) + REVEAL_OPEN) revert OutsideWindow();
        if (sha256(abi.encodePacked(root, salt)) != w.commitment) revert CommitmentMismatch();
        w.root = root;
        w.revealedAt = uint40(block.timestamp);
        emit Revealed(weekId, root, salt);
    }

    /// @notice The agent posts its own grade ONCE; anyone can recompute it from the revealed forecasts + real opens.
    function grade(uint64 weekId, int32 hitBps, int32 brierBps) external onlyAgent {
        Week storage w = forecastWeeks[weekId];
        if (w.revealedAt == 0 || w.gradedAt != 0) revert BadState();
        if (hitBps < 0 || hitBps > 10_000 || brierBps < 0 || brierBps > 10_000) revert BadScore();
        w.hitBps = hitBps;
        w.brierBps = brierBps;
        w.gradedAt = uint40(block.timestamp);
        emit Graded(weekId, hitBps, brierBps);
    }

    /// @notice Prove one forecast. Takes the leaf PREIMAGE (e.g. "2026-10-09|NVDA|-35.2|0.4123"), not a bare hash,
    ///         and requires it to start with this week's "YYYY-MM-DD|" prefix, so an inner node can never be passed
    ///         off as a leaf (second-preimage attack on the old verifyForecast(bytes32 leaf, ...)).
    function verifyForecast(uint64 weekId, string calldata preimage, bytes32[] calldata proof)
        external
        view
        returns (bool)
    {
        bytes32 root = forecastWeeks[weekId].root;
        if (root == bytes32(0)) return false;
        bytes memory pre = bytes(preimage);
        bytes11 prefix = weekPrefix(weekId);
        if (pre.length <= 11) return false;
        for (uint256 i = 0; i < 11; i++) {
            if (pre[i] != prefix[i]) return false;
        }
        bytes32 h = sha256(pre);
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 o = proof[i];
            h = h < o ? sha256(abi.encodePacked(h, o)) : sha256(abi.encodePacked(o, h));
        }
        return h == root;
    }

    // ------------------------------------------------------------------ date helpers

    /// @return the unix timestamp of 00:00 UTC on the Friday encoded by weekId (yyyymmdd). Reverts if not a Friday.
    function fridayStart(uint64 weekId) public pure returns (uint256) {
        uint256 y = weekId / 10_000;
        uint256 m = (weekId / 100) % 100;
        uint256 d = weekId % 100;
        if (y < 2024 || y > 2100 || m < 1 || m > 12 || d < 1 || d > 31) revert BadWeekId();
        uint256 days_ = _daysFromCivil(y, m, d);
        if (days_ % 7 != 1) revert BadWeekId(); // 1970-01-01 was a Thursday, so Fridays are days % 7 == 1
        return days_ * 1 days;
    }

    /// @return out the 11 bytes "YYYY-MM-DD|" for weekId, the prefix modulus/oracle.py puts on every leaf.
    function weekPrefix(uint64 weekId) public pure returns (bytes11 out) {
        bytes memory b = new bytes(11);
        uint256 y = weekId / 10_000;
        uint256 m = (weekId / 100) % 100;
        uint256 d = weekId % 100;
        b[0] = bytes1(uint8(48 + (y / 1000) % 10));
        b[1] = bytes1(uint8(48 + (y / 100) % 10));
        b[2] = bytes1(uint8(48 + (y / 10) % 10));
        b[3] = bytes1(uint8(48 + y % 10));
        b[4] = "-";
        b[5] = bytes1(uint8(48 + m / 10));
        b[6] = bytes1(uint8(48 + m % 10));
        b[7] = "-";
        b[8] = bytes1(uint8(48 + d / 10));
        b[9] = bytes1(uint8(48 + d % 10));
        b[10] = "|";
        assembly {
            out := mload(add(b, 32))
        }
    }

    /// Howard Hinnant's days_from_civil, valid for the guarded range above.
    function _daysFromCivil(uint256 y, uint256 m, uint256 d) private pure returns (uint256) {
        if (m <= 2) y -= 1;
        uint256 era = y / 400;
        uint256 yoe = y - era * 400;
        uint256 mp = m > 2 ? m - 3 : m + 9;
        uint256 doy = (153 * mp + 2) / 5 + d - 1;
        uint256 doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
        return era * 146_097 + doe - 719_468;
    }
}
