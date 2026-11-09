"""Provider boundary: simulation is the only shipped implementation.
Adapters return typed events; they have no authority to book, contact, settle or
change state. The application validates and approves their commands.
"""
from typing import Protocol,Literal
from dataclasses import dataclass
import random
@dataclass(frozen=True)
class Outcome:
    code:Literal['delivered','NDR']
    simulated:bool=True
    rule_version:str='simulation-v1'
class CourierConnector(Protocol):
    def outcome(self,seed:int,rto_basis_points:int)->Outcome: ...
class SimulationCourier:
    def outcome(self,seed:int,rto_basis_points:int=2000)->Outcome:
        return Outcome('NDR' if random.Random(seed).randrange(10000)<rto_basis_points else 'delivered')
    def poll(self,inject_timeout=False):
        if inject_timeout: raise TimeoutError('SIMULATED_CONNECTOR_TIMEOUT')
        return {'source':'simulation','status':'polled','simulated':True}
