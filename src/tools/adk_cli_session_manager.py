"""
ADK CLI Session Manager - Interactive Subprocess Approach

This manages persistent ADK CLI processes (one per Agentix session).
Each process runs `adk run <agent> --save_session --session_id <id>` and stays alive,
maintaining full agent state in memory without needing manual serialization.

Key benefits:
- No manual state management (ADK handles everything)
- No global variable injection/capture complexity
- Real-time interactive communication
- Natural session lifecycle (process = session)
"""

import os
import sys
import subprocess
import threading
import queue
import re
import time
from pathlib import Path
from typing import Dict, Optional, Any
from dotenv import load_dotenv


class ADKCLISession:
    """
    Manages a single persistent ADK CLI process for an agent.
    
    The process runs interactively and maintains all agent state in memory.
    Queries are sent via stdin, responses read from stdout.
    """
    
    def __init__(self, agent_name: str, session_id: str, agents_dir: Path):
        self.agent_name = agent_name
        self.session_id = session_id
        self.agents_dir = agents_dir
        self.process: Optional[subprocess.Popen] = None
        self.output_queue = queue.Queue()
        self.reader_thread: Optional[threading.Thread] = None
        self.running = False
        
    def start(self):
        """Start the ADK CLI process."""
        cmd = [
            "adk", "run", self.agent_name,
            "--save_session",
            "--session_id", self.session_id
        ]
        
        print(f"\n{'='*60}")
        print(f"🚀 Starting ADK CLI session: {self.agent_name}")
        print(f"   Session ID: {self.session_id}")
        print(f"   Command: {' '.join(cmd)}")
        print(f"{'='*60}")
        
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            cwd=str(self.agents_dir),
            env=os.environ.copy()
        )
        
        self.running = True
        
        # Start background thread to read output
        self.reader_thread = threading.Thread(
            target=self._read_output,
            daemon=True
        )
        self.reader_thread.start()
        
        # Wait for initial prompt
        self._wait_for_ready()
        
        print(f"✅ CLI session ready")
        
    def _read_output(self):
        """Background thread to read process output line by line."""
        try:
            while self.running and self.process and self.process.poll() is None:
                line = self.process.stdout.readline()
                if line:
                    self.output_queue.put(('stdout', line))
                else:
                    time.sleep(0.1)
        except Exception as e:
            self.output_queue.put(('error', str(e)))
    
    def _wait_for_ready(self, timeout=60):
        """Wait for the CLI to show it's ready (logs are set up)."""
        start_time = time.time()
        seen_lines = []
        
        while time.time() - start_time < timeout:
            try:
                msg_type, line = self.output_queue.get(timeout=2)
                if msg_type == 'stdout':
                    seen_lines.append(line)
                    
                    # Look for various ready indicators
                    line_lower = line.lower()
                    if any(indicator in line_lower for indicator in [
                        'type exit to exit',
                        'running agent',
                        '[user]:',  # Prompt appeared
                    ]):
                        # Drain any remaining startup messages
                        time.sleep(1)
                        self._drain_queue()
                        print(f"✅ CLI session ready (saw {len(seen_lines)} startup lines)")
                        return
            except queue.Empty:
                # Check if we've seen at least the "Running agent" line and some output
                if len(seen_lines) > 3:
                    # Likely ready, just didn't see explicit prompt yet
                    time.sleep(0.5)
                    self._drain_queue()
                    print(f"✅ CLI session ready (inferred from {len(seen_lines)} lines)")
                    return
                continue
        
        # Show what we saw for debugging
        print(f"⚠️  Timeout waiting for CLI ready. Saw {len(seen_lines)} lines:")
        for line in seen_lines[-10:]:  # Last 10 lines
            print(f"   {line.rstrip()}")
        raise TimeoutError("CLI did not become ready in time")
    
    def _drain_queue(self):
        """Drain all pending messages from queue."""
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break
    
    def query(self, query_text: str, timeout=120) -> str:
        """
        Send a query to the agent and get response.
        
        Args:
            query_text: Natural language query
            timeout: Max seconds to wait for response
            
        Returns:
            Agent's response text
        """
        if not self.running or not self.process:
            raise RuntimeError("Session is not running")
        
        print(f"\n{'='*60}")
        print(f"📤 Sending query to {self.agent_name}")
        print(f"   Query: {query_text[:100]}...")
        print(f"{'='*60}")
        
        # Clear any pending output
        self._drain_queue()
        
        # Send query
        self.process.stdin.write(query_text + "\n")
        self.process.stdin.flush()
        
        # Collect response until we see the next prompt or timeout
        response_lines = []
        start_time = time.time()
        
        # Track what we've seen
        saw_query_echo = False
        lines_since_last = 0
        max_idle_lines = 5  # If we see 5 empty lines, assume done
        
        while time.time() - start_time < timeout:
            try:
                msg_type, line = self.output_queue.get(timeout=2)
                
                if msg_type == 'error':
                    raise RuntimeError(f"Process error: {line}")
                
                if msg_type == 'stdout':
                    # Skip echo of user input
                    if not saw_query_echo and query_text in line:
                        saw_query_echo = True
                        continue
                    
                    # Check if this is the next prompt (indicates response is complete)
                    if re.match(r'\[user\]:\s*$', line.strip()):
                        print(f"🔍 Detected prompt, response complete")
                        break
                    
                    # Track empty lines
                    if line.strip() == "":
                        lines_since_last += 1
                        if lines_since_last >= max_idle_lines and response_lines:
                            print(f"🔍 Multiple empty lines, assuming response complete")
                            break
                        continue
                    else:
                        lines_since_last = 0
                    
                    # Collect response lines
                    # Skip the [user]: prefix and agent name prefix if present
                    cleaned_line = re.sub(r'^\[user\]:\s*', '', line.rstrip())
                    cleaned_line = re.sub(r'^\[[\w_]+\]:\s*', '', cleaned_line)  # Strip [agent_name]:
                    
                    if cleaned_line:
                        response_lines.append(cleaned_line)
                        print(f"📝 Collected line {len(response_lines)}: {cleaned_line[:80]}...")
                        
            except queue.Empty:
                # If we have content and haven't seen anything for 2 seconds, consider it done
                if response_lines and time.time() - start_time > 5:
                    print(f"🔍 Timeout with {len(response_lines)} lines collected, assuming complete")
                    break
                
                # Check if process died
                if self.process.poll() is not None:
                    raise RuntimeError("Process terminated unexpectedly")
                continue
        
        response = '\n'.join(response_lines).strip()
        
        print(f"✅ Response received: {len(response)} chars, {len(response_lines)} lines")
        print(f"{'='*60}\n")
        
        return response
    
    def stop(self):
        """Stop the CLI process gracefully."""
        if not self.running:
            return
        
        print(f"\n🛑 Stopping CLI session: {self.agent_name} ({self.session_id})")
        
        self.running = False
        
        if self.process:
            try:
                # Try graceful exit first
                self.process.stdin.write("exit\n")
                self.process.stdin.flush()
                self.process.wait(timeout=5)
            except:
                # Force kill if needed
                self.process.kill()
                self.process.wait()
        
        print(f"✅ Session stopped")
    
    def is_alive(self) -> bool:
        """Check if process is still running."""
        return self.running and self.process and self.process.poll() is None


class ADKCLISessionManager:
    """
    Manages multiple ADK CLI sessions (one per Agentix chat session).
    
    Maps session_id -> ADKCLISession process.
    """
    
    def __init__(self, agents_dir: Optional[Path] = None):
        if agents_dir is None:
            # Default to PnP_agents directory
            current_dir = Path(__file__).parent.parent.parent.parent.parent
            agents_dir = current_dir / "PnP_agents"
        
        self.agents_dir = Path(agents_dir)
        self.sessions: Dict[str, ADKCLISession] = {}
        
        # Load .env for proxy settings
        env_file = self.agents_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=True)
            print(f"✅ Loaded .env from: {env_file}")
    
    def get_session_key(self, agent_name: str, session_id: str) -> str:
        """Get unique key for session."""
        return f"{agent_name}_{session_id}"
    
    def query_agent(self, agent_name: str, session_id: str, query: str) -> Dict[str, Any]:
        """
        Query an agent through its persistent CLI session.
        
        Creates session on first query, reuses for subsequent queries.
        """
        session_key = self.get_session_key(agent_name, session_id)
        
        # Get or create session
        if session_key not in self.sessions or not self.sessions[session_key].is_alive():
            session = ADKCLISession(agent_name, session_id, self.agents_dir)
            session.start()
            self.sessions[session_key] = session
        
        session = self.sessions[session_key]
        
        # Send query and get response
        response_text = session.query(query)
        
        return {
            "response": response_text,
            "session_id": session_id,
            "agent_name": agent_name
        }
    
    def reset_session(self, agent_name: str, session_id: str) -> Dict[str, Any]:
        """Stop and remove a session."""
        session_key = self.get_session_key(agent_name, session_id)
        
        if session_key in self.sessions:
            self.sessions[session_key].stop()
            del self.sessions[session_key]
            return {"success": True, "message": f"Session {session_id} reset"}
        
        return {"success": False, "message": "Session not found"}
    
    def cleanup(self):
        """Stop all sessions."""
        for session in self.sessions.values():
            session.stop()
        self.sessions.clear()


# Singleton instance
_manager: Optional[ADKCLISessionManager] = None

def get_session_manager() -> ADKCLISessionManager:
    """Get the global session manager instance."""
    global _manager
    if _manager is None:
        _manager = ADKCLISessionManager()
    return _manager
