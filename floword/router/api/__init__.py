from .config import router as config
from .v1.conversation import router as v1_conversation
from .v1.workflow import router as v1_workflow

routers = [v1_conversation, v1_workflow, config]
