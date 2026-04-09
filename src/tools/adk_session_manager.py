"""
ADK Session Manager - Hybrid Programmatic Approach with Explicit State Management

This approach combines:
- Speed of programmatic calls (no subprocess overhead)
- Reliability of explicit state persistence (files, not module globals)

Key Design:
- Each session has a state file: {agent}_{session_id}.state.json
- State file contains: DATAFRAMES_STORAGE, CONTEXT_INVENTORY, etc.
- Before query: Load state file → Inject into agent module globals
- After query: Capture agent module globals → Save to state file
- Session events are preserved normally in session JSON
"""

import os
import sys
import json
import copy
import asyncio
import importlib.util
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

from google.genai import types
from google.adk.apps.app import App
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.sessions.session import Session
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.auth.credential_service.in_memory_credential_service import InMemoryCredentialService


class ADKSessionManager:
    """
    Manages ADK agent sessions with explicit state persistence.
    
    State is stored in separate .state.json files and injected/captured
    from agent module globals for each query.
    """
    
    def __init__(self, agents_dir: Optional[Path] = None):
        if agents_dir is None:
            current_dir = Path(__file__).parent.parent.parent.parent.parent
            agents_dir = current_dir / "new_v2_agents" / "PnP_agents"
        
        self.agents_dir = Path(agents_dir)
        self.sessions_dir = self.agents_dir / "sessions"
        self.sessions_dir.mkdir(exist_ok=True)
        
        self.loaded_agents: Dict[str, Dict[str, Any]] = {}
        
        # Load .env for proxy settings
        env_file = self.agents_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=True)
            print(f"✅ Loaded .env from: {env_file}")
    
    def _get_session_file_path(self, agent_name: str, session_id: str) -> Path:
        """Get path to session JSON file."""
        return self.sessions_dir / f"{agent_name}_{session_id}.session.json"
    
    def _get_state_file_path(self, agent_name: str, session_id: str) -> Path:
        """Get path to state file (separate from session)."""
        return self.sessions_dir / f"{agent_name}_{session_id}.state.json"
    
    def _load_agent(self, agent_name: str) -> Dict[str, Any]:
        """Load agent and its MCP server module."""
        if agent_name in self.loaded_agents:
            return self.loaded_agents[agent_name]
        
        agent_path = self.agents_dir / agent_name
        if not agent_path.exists():
            raise ValueError(f"Agent directory not found: {agent_path}")
        
        agent_path_str = str(agent_path)
        if agent_path_str not in sys.path:
            sys.path.insert(0, agent_path_str)
        
        try:
            # Load agent.py
            spec = importlib.util.spec_from_file_location(
                f"{agent_name}_agent",
                agent_path / "agent.py"
            )
            agent_module = importlib.util.module_from_spec(spec)
            sys.modules[f"{agent_name}_agent"] = agent_module
            spec.loader.exec_module(agent_module)
            
            # Load mcp/server.py
            mcp_spec = importlib.util.spec_from_file_location(
                f"{agent_name}_mcp_server",
                agent_path / "mcp" / "server.py"
            )
            mcp_server_module = importlib.util.module_from_spec(mcp_spec)
            sys.modules[f"{agent_name}_mcp_server"] = mcp_server_module
            mcp_spec.loader.exec_module(mcp_server_module)
            
            self.loaded_agents[agent_name] = {
                "root_agent": agent_module.root_agent,
                "mcp_server_module": mcp_server_module
            }
            
            print(f"✅ Loaded agent: {agent_name}")
            return self.loaded_agents[agent_name]
            
        except Exception as e:
            raise RuntimeError(f"Failed to load agent '{agent_name}': {e}")
    
    def _load_state_from_file(self, state_file: Path) -> Dict[str, Any]:
        """Load agent state from file."""
        if not state_file.exists():
            return {}
        
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            print(f"📥 Loaded state from: {state_file.name}")
            return state
        except Exception as e:
            print(f"⚠️  Failed to load state: {e}")
            return {}
    
    def _save_state_to_file(self, state: Dict[str, Any], state_file: Path):
        """Save agent state to file."""
        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
            print(f"💾 Saved state to: {state_file.name}")
        except Exception as e:
            print(f"❌ Failed to save state: {e}")
    
    def _inject_state(self, mcp_server_module, state: Dict[str, Any]):
        """Inject state into agent module globals."""
        if not state:
            return
        
        # Inject DATAFRAMES_STORAGE
        if "DATAFRAMES_STORAGE" in state and hasattr(mcp_server_module, "DATAFRAMES_STORAGE"):
            mcp_server_module.DATAFRAMES_STORAGE.clear()
            mcp_server_module.DATAFRAMES_STORAGE.update(state["DATAFRAMES_STORAGE"])
            print(f"📥 Restored {len(state['DATAFRAMES_STORAGE'])} DataFrames")
        
        # Inject CONTEXT_INVENTORY
        if "CONTEXT_INVENTORY" in state and hasattr(mcp_server_module, "CONTEXT_INVENTORY"):
            mcp_server_module.CONTEXT_INVENTORY.clear()
            mcp_server_module.CONTEXT_INVENTORY.update(state["CONTEXT_INVENTORY"])
            print(f"📥 Restored context inventory")
    
    def _capture_state(self, mcp_server_module) -> Dict[str, Any]:
        """Capture state from agent module globals."""
        state = {}
        
        # Capture DATAFRAMES_STORAGE
        if hasattr(mcp_server_module, "DATAFRAMES_STORAGE"):
            state["DATAFRAMES_STORAGE"] = dict(mcp_server_module.DATAFRAMES_STORAGE)
            print(f"📤 Captured {len(state['DATAFRAMES_STORAGE'])} DataFrames")
        
        # Capture CONTEXT_INVENTORY
        if hasattr(mcp_server_module, "CONTEXT_INVENTORY"):
            state["CONTEXT_INVENTORY"] = copy.deepcopy(mcp_server_module.CONTEXT_INVENTORY)
            print(f"📤 Captured context inventory")
        
        return state
    
    def _load_session_from_file(self, session_file: Path) -> Optional[Session]:
        """Load session from JSON file."""
        if not session_file.exists():
            return None
        
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                session = Session.model_validate_json(f.read())
            print(f"📂 Loaded session with {len(session.events)} events")
            return session
        except Exception as e:
            print(f"⚠️  Failed to load session: {e}")
            return None
    
    def _save_session_to_file(self, session: Session, session_file: Path):
        """Save session to JSON file."""
        try:
            with open(session_file, 'w', encoding='utf-8') as f:
                f.write(session.model_dump_json(indent=2, exclude_none=True))
            print(f"💾 Saved session with {len(session.events)} events")
        except Exception as e:
            print(f"❌ Failed to save session: {e}")
    
    async def query_agent(self, agent_name: str, session_id: str, query: str) -> Dict[str, Any]:
        """Query agent with full state management."""
        print(f"\n{'='*60}")
        print(f"🔍 Query Agent: {agent_name}")
        print(f"   Session: {session_id}")
        print(f"   Query: {query[:100]}...")
        print(f"{'='*60}")
        
        try:
            # 1. Get file paths
            session_file = self._get_session_file_path(agent_name, session_id)
            state_file = self._get_state_file_path(agent_name, session_id)
            
            # 2. Load agent
            agent_data = self._load_agent(agent_name)
            root_agent = agent_data["root_agent"]
            mcp_server_module = agent_data["mcp_server_module"]
            
            # 3. Load and inject state FIRST
            state = self._load_state_from_file(state_file)
            self._inject_state(mcp_server_module, state)
            
            # 4. Load session
            saved_session = self._load_session_from_file(session_file)
            
            if saved_session:
                app_name = saved_session.app_name
                user_id = saved_session.user_id
                previous_events = saved_session.events
            else:
                app_name = agent_name
                user_id = f"agentix_user_{session_id}"
                previous_events = []
            
            # 5. Initialize services
            session_service = InMemorySessionService()
            artifact_service = InMemoryArtifactService()
            credential_service = InMemoryCredentialService()
            
            # 6. Create session and restore events
            session = await session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                state={"_time": datetime.now().isoformat()}
            )
            
            for event in previous_events:
                await session_service.append_event(session, event)
            
            print(f"✅ Session restored with {len(previous_events)} events")
            
            # 7. Run query
            app = App(name=app_name, root_agent=root_agent)
            runner = Runner(
                app=app,
                session_service=session_service,
                artifact_service=artifact_service,
                credential_service=credential_service
            )
            
            content = types.Content(role='user', parts=[types.Part(text=query)])
            
            print(f"🤖 Running query...")
            response_text = ""
            async for event in runner.run_async(
                user_id=session.user_id,
                session_id=session.id,
                new_message=content
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            if event.author != "user":
                                response_text += part.text
            
            print(f"✅ Response: {len(response_text)} chars")
            
            # 8. Get updated session
            updated_session = await session_service.get_session(
                app_name=session.app_name,
                user_id=session.user_id,
                session_id=session.id
            )
            
            # 9. Capture and save state
            new_state = self._capture_state(mcp_server_module)
            self._save_state_to_file(new_state, state_file)
            
            # 10. Save session
            self._save_session_to_file(updated_session, session_file)
            
            print(f"{'='*60}\n")
            
            return {
                "response": response_text.strip(),
                "session_id": session_id,
                "events_count": len(updated_session.events)
            }
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            raise


# Singleton
_manager: Optional[ADKSessionManager] = None

def get_session_manager() -> ADKSessionManager:
    """Get global session manager instance."""
    global _manager
    if _manager is None:
        _manager = ADKSessionManager()
    return _manager
