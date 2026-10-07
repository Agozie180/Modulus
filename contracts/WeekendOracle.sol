// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

/// @title WeekendOracle - Modulus seals its Monday-open forecasts on BNB Chain before Wall Street wakes.
/// @notice commit() during the dark weekend (Fri 20:00 UTC - Sun 22:00 UTC), reveal() after Monday's
///         13:30 UTC open, then anyone can prove any single forecast with a Merkle proof and grade it.
///         commitment = sha256(merkleRoot || salt); leaf = sha256("week|ticker|gapHatBps|pUp").
///         Inner nodes = sha256(min(a,b) || max(a,b)) (sorted pairs), matching modulus/oracle.py.
contract WeekendOracle {
    struct Week { bytes32 commitment; bytes32 root; uint64 committedAt; uint64 revealedAt; int32 hitBps; int32 brierBps; }

    address public immutable agent;            // the Modulus agent wallet (ERC-8004 identity owner)
    mapping(uint64 => Week) public weeks;       // weekId = Friday as yyyymmdd

    event Committed(uint64 indexed weekId, bytes32 commitment, uint256 nForecasts);
    event Revealed(uint64 indexed weekId, bytes32 root, bytes32 salt);
    event Graded(uint64 indexed weekId, int32 hitBps, int32 brierBps);

    constructor() { agent = msg.sender; }

    modifier onlyAgent() { require(msg.sender == agent, "not agent"); _; }

    function commit(uint64 weekId, bytes32 commitment, uint256 nForecasts) external onlyAgent {
        require(weeks[weekId].committedAt == 0, "already committed");   // no edits, ever
        weeks[weekId].commitment = commitment;
        weeks[weekId].committedAt = uint64(block.timestamp);
        emit Committed(weekId, commitment, nForecasts);
    }

    function reveal(uint64 weekId, bytes32 root, bytes32 salt) external onlyAgent {
        Week storage w = weeks[weekId];
        require(w.committedAt != 0 && w.revealedAt == 0, "bad state");
        require(sha256(abi.encodePacked(root, salt)) == w.commitment, "root/salt do not match commitment");
        w.root = root;
        w.revealedAt = uint64(block.timestamp);
        emit Revealed(weekId, root, salt);
    }

    /// @notice the agent posts its own grade; anyone can recompute it from the revealed forecasts + real opens.
    function grade(uint64 weekId, int32 hitBps, int32 brierBps) external onlyAgent {
        require(weeks[weekId].revealedAt != 0, "reveal first");
        weeks[weekId].hitBps = hitBps;
        weeks[weekId].brierBps = brierBps;
        emit Graded(weekId, hitBps, brierBps);
    }

    function verifyForecast(uint64 weekId, bytes32 leaf, bytes32[] calldata proof) external view returns (bool) {
        bytes32 h = leaf;
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 o = proof[i];
            h = h < o ? sha256(abi.encodePacked(h, o)) : sha256(abi.encodePacked(o, h));
        }
        return h == weeks[weekId].root && h != bytes32(0);
    }
}
