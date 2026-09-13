"""R control facts, independent of execution and business strategy implementations."""
from .storage import StoreBase
from .registration import Registration
from .responsibilities import Responsibilities
from .facilities import Facilities
from .decisions import Decisions
from .holders import Holders
from .wait_barriers import WaitBarriers
from .installations import Installations
from .restores import Restores
from .values import ControlError

class ControlStore(Registration,Responsibilities,Facilities,Decisions,Holders,WaitBarriers,Installations,Restores,StoreBase):
    """Trusted host-owned SQLite control store; reference authority is explicitly injected."""

__all__=['ControlStore','ControlError']
