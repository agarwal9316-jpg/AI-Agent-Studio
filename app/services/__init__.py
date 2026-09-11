"""Services package - re-exports from core.services for backward compatibility."""

# Core services modules (always available)
from app.core.services import ai
from app.core.services import chat
from app.core.services import company
from app.core.services import data
from app.core.services import integrations
from app.core.services import llm
from app.core.services import misc
from app.core.services import system
from app.core.services import tools
from app.core.services import web

# Direct exports that don't cause circular imports
from app.core.services.chat import chat_store
from app.core.services.chat import memory_store
from app.core.services.chat import notes_store
from app.core.services.chat import automations_store
from app.core.services.company import company_store
from app.core.services.company import org_comms
from app.core.services.company import org_tools
from app.core.services.data import agent_tracker
from app.core.services.data import audit_log
from app.core.services.data import project_outputs
from app.core.services.data import project_store
from app.core.services.data import rag_knowledge
from app.core.services.data import storage
from app.core.services.data import usage_meter
from app.core.services.system import clipboard_watch
from app.core.services.system import file_watcher
from app.core.services.system import global_hotkeys
from app.core.services.system import system_tray
from app.core.services.system import branding
from app.core.services.system import scheduler_service
from app.core.services.company import team_bg
from app.core.services.company import team_channel
from app.core.services.ai import local_embeddings
from app.core.services.ai import self_improve
from app.core.services.ai import train_lab
from app.core.services.llm import providers
from app.core.services.llm import model_profiles
from app.core.services.llm import ollama_local
from app.core.services.misc import artifacts
from app.core.services.misc import artifacts_store
from app.core.services.misc import studio_bundle
from app.core.services.misc import patch_review
from app.core.services.misc import prompt_library
from app.core.services.misc import workflow_graph
from app.core.services.misc import flow_canvas
from app.core.services.tools import tool_approvals
from app.core.services.tools import tool_budget
from app.core.services.system import ops_monitor

# Modules that cause circular imports - lazy loaded via __getattr__
_LAZY_MODULES = {
    "org_execution": ("app.core.services.company", "org_execution"),
}

__all__ = [
    # Core modules
    "ai",
    "chat",
    "company",
    "data",
    "integrations",
    "llm",
    "misc",
    "system",
    "tools",
    "web",
    # Direct exports
    "chat_store",
    "memory_store",
    "notes_store",
    "automations_store",
    "company_store",
    "org_comms",
    "org_tools",
    "agent_tracker",
    "audit_log",
    "project_outputs",
    "project_store",
    "rag_knowledge",
    "storage",
    "usage_meter",
    "clipboard_watch",
    "file_watcher",
    "global_hotkeys",
    "system_tray",
    "branding",
    "scheduler_service",
    "team_bg",
    "team_channel",
    "local_embeddings",
    "providers",
    "model_profiles",
    "ollama_local",
    "artifacts",
    "artifacts_store",
    "studio_bundle",
    "patch_review",
    "prompt_library",
    "self_improve",
    "tool_approvals",
    "tool_budget",
    "ops_monitor",
    "train_lab",
    # Lazy-loaded (circular import safe)
    "org_execution",
    "workflow_graph",
    "flow_canvas",
]


def __getattr__(name: str):
    """Lazy load modules that cause circular imports."""
    if name in _LAZY_MODULES:
        module_path, attr_name = _LAZY_MODULES[name]
        module = __import__(module_path, fromlist=[attr_name])
        return getattr(module, attr_name)
    raise AttributeError(f"module 'app.services' has no attribute '{name}'")
