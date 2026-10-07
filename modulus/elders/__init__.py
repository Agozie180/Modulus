from .gap import GapElder
from .whale import WhaleElder
from .arbiter import ArbiterElder
from .value import ValueElder
from .sentinel import SentinelElder

COUNCIL = [GapElder(), WhaleElder(), ArbiterElder(), ValueElder(), SentinelElder()]
