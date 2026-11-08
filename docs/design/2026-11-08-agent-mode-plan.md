# Agent mode: turning Locus chat into a task-doing agent

| | |
|---|---|
| **Date** | 2026-11-08 |
| **Status** | Plan, not started |
| **Owner** | Locus team |
| **Scope** | Desktop app, browser GUI and terminal chat |

> **For agents picking this up cold:** read §1 and §2 first. Each phase in §4 lists the files it touches and what "done" means, and phases 1–3 must land in order. Phases 4, 5 and 6 are independent of each other once phase 3 is in.

## 1. Goal

Today Locus chat answers questions. The goal is for the same chat box, by text or voice, to **carry out tasks** on the user's machine: open and organize files, run commands, drive the browser, control the desktop, draft and send email after approval, and work through multi-step developer tasks. Everything stays local by default and every risky step needs the user's approval.

**Success looks like:** a user says "Find last month's invoices in Downloads, move them into Documents/Invoices and summarize the totals." Locus shows a short plan, runs the steps with visible progress, asks before moving files, and answers aloud with the result.

## 2. What already exists

Most of the agent machinery is in the repo. The gap is mostly wiring and UX.

| Area | What's there | Where |
|---|---|---|
| Agent loops | `orchestrator`, `native_react`, `native_openhands` (CodeAct), `operative`, `deep_research`, `monitor_operative`, all with `max_turns` | `src/locus/agents/` |
| Tools | ~40 tools: `shell_exec`, `file_read`/`file_write`, `apply_patch`, `git_tool`, `browser` + `browser_axtree`, `code_interpreter` (+ Docker), `web_search`, `http_request`, `memory_manage`, `pdf_tool`, `apple_calendar`, `mcp_adapter`, `text_to_speech` | `src/locus/tools/` |
| Agent streaming | `AgentStreamBridge` streams agent events over SSE | `src/locus/server/stream_bridge.py` |
| Approvals | `ApprovalStore` (pending actions + permission rules), REST routes, `ApprovalBell` UI | `src/locus/tools/approval_store.py`, `src/locus/server/approval_routes.py`, `frontend/src/components/ApprovalBell.tsx` |
| Security | Capability policy, guardrails, injection scanner, subprocess sandbox, SSRF guard, audit log, taint tracking | `src/locus/security/` |
| Speech to text | faster-whisper, OpenAI Whisper, Deepgram; push-to-talk in UI | `src/locus/speech/`, `frontend/src/hooks/useSpeech.ts` |
| Text to speech | Kokoro (local), ElevenLabs, Cartesia, OpenAI | `src/locus/speech/` |
| Tool call UI | Tool call cards in chat, trace debugger | `frontend/src/components/Chat/ToolCallCard.tsx`, `.../TraceDebugger.tsx` |
| Quick overlay | Small chat overlay window | `desktop/src-tauri/src/overlay.html` |
| Model sizing | RAM-based model ladder (`qwen3.5:0.8b` → `122b`), startup model `qwen3.5:4b`, fallback `qwen3:0.6b` | `frontend/src-tauri/src/lib.rs` |

## 3. Gaps that stop it acting as an agent

1. **The desktop chat runs the no-tools agent.** The desktop app starts the server with `--agent simple` (`frontend/src-tauri/src/lib.rs`), so its chat never calls tools. (`locus serve` on its own defaults to `orchestrator` with `think`, `calculator` and `web_search`.)
2. **Rich requests bypass the agent.** `chat_completions` in `src/locus/server/routes.py` sends any request with images, attachments or web search straight to the engine, because agents take only the latest message's text. Non-streaming requests use the agent only when it has tools.
3. **No in-chat task flow.** Approvals live in a bell, not in the conversation. There's no visible plan, step progress, cancel or resume.
4. **No desktop control.** No tools to open apps, manage windows, change volume or brightness, use the clipboard, show notifications or take screenshots. Only the browser can be driven.
5. **Voice is push-to-talk only.** No hotkey or wake word, no end-of-speech detection, replies aren't spoken automatically, and the user can't interrupt.
6. **Small models are unreliable at tool calls.** The RAM ladder picks 0.8b–4b on 4–8 GB machines; those miss or garble tool calls on multi-step tasks.

## 4. Phases

### Phase 1: agent mode in chat (foundation)

**Goal:** chat can call tools, with a switch between "Chat" and "Agent".

> **Status (2026-11-08): implemented.** As built:
> - The request field is `mode: "chat" | "agent"`. Leaving it unset keeps the old routing, so `locus gui` users on the `orchestrator` default see no change.
> - `src/locus/server/task_agent.py` reuses the configured agent if it has tools. Otherwise it builds one `orchestrator` the first time it's needed and caches it on `app.state.task_agent`.
> - The tool set is `think`, `calculator`, `file_read`, `pdf_extract` and `memory_manage`. `file_read` is kept to the home folder unless `security.allowed_dirs` is set. `file_write` and `shell_exec` wait for phase 3, because the server has no way to ask for approval yet (`shell_exec` requires confirmation and is refused there).
> - Prior messages already reached agents through `AgentContext.conversation`, so no change was needed there.
> - Agent streams now forward that agent's `agent_turn_start`, `tool_call_start` and `tool_call_end` events live. Events from other agents on the bus are filtered out.
> - The small-model notice is a check on the model's name in the frontend (`isSmallForAgent`: under 4B).
> - With web search or attachments in the conversation, the UI says Agent mode can't use them yet and gives a chat answer. Phase 2 removes that limit.

- Add an `agent` mode to the chat request (`ChatCompletionRequest` in `src/locus/server/models.py`), defaulting to the configured agent. Keep `simple` available as "Chat" mode.
- Add a starter preset `assistant` (`orchestrator` + a safe default tool set: `file_read`, `file_write`, `shell_exec`, `web_search`, `browser`, `memory_manage`, `calculator`, `think`). Make it the desktop app's default on first launch; existing users keep their config.
- Build the agent per request (or per session) instead of only once at server start, so the UI's mode switch takes effect without a restart. Check `app.state.agent` usage in `routes.py` and `agent_manager_routes.py`.
- Give the agent the full conversation, not only the last message.
- **Frontend:** add a Chat/Agent toggle to `InputArea.tsx`; persist it per conversation.
- **Model check:** before running in agent mode, check whether the model supports tool calling (extend `src/locus/server/model_capabilities.py`). If it doesn't, or it's under ~4B, show a one-line notice suggesting a bigger model.

**Done when:** in agent mode, "what files are in my Downloads folder?" calls `file_read`/`shell_exec` and the tool call card appears; chat mode behaves exactly as today; tests cover both paths.

### Phase 2: attachments and web search through the agent

**Goal:** attachments, images and web search work in agent mode instead of silently falling back to plain chat.

- Turn attachments into agent context: attached document text goes in as context or as a `file_read`-style handle; images go to vision models as today.
- Expose web search to the agent as its normal `web_search` tool when the toggle is on, rather than pre-injecting results. The agent decides when to search, and the privacy rule stays the same (off unless the user turns it on).
- Remove the `has_extras` bypass in `routes.py` once both paths are covered.

**Done when:** "summarize this PDF and email the summary to me" works with an attachment in agent mode; the existing attachment and web-search tests pass in both modes.

### Phase 3: task flow and approvals in the conversation

**Goal:** the user sees what the agent plans, what it's doing and what it needs approved, without leaving the chat.

- **Plan step:** for multi-step requests, the agent first emits a short plan (a new stream event type in `stream_bridge.py`); the UI shows it as a checklist that ticks off as steps finish.
- **Inline approvals:** when a tool needs approval, stream an `approval_required` event carrying the action from `ApprovalStore`; render Approve, Deny and "Always allow for this folder/command" buttons in the message. Keep `ApprovalBell` for background agents.
- **Risk levels:** classify tools as read-only (no prompt), reversible write (prompt once per session or per folder) or irreversible/outward (always prompt: delete, send, purchase, system settings). Reuse `severity_policy.py` and `capabilities.py`.
- **Cancel and resume:** a Stop button that cancels the running agent cleanly; the session store keeps enough state to continue with "keep going".
- **Undo:** for file moves and renames, record the inverse operation and offer Undo in the result.
- **Raise `max_turns`** for agent mode (for example 25), with the loop guard (`loop_guard.py`) catching repeated calls.

**Done when:** the invoice example from §1 runs end to end with a visible plan, one approval prompt and a working Undo; Stop interrupts within a second; risky tools can't run without approval (tested).

### Phase 4: desktop control tools

**Goal:** the agent can operate the computer, not only files and the browser.

New tools under `src/locus/tools/desktop/`, one module per OS behind a common interface (Windows first, since that's where the desktop app is most used, then macOS, then Linux):

| Tool | Actions | Risk |
|---|---|---|
| `app_control` | Open, focus, close apps; list running apps | Reversible (close = prompt) |
| `window_control` | List, move, resize, minimize, snap windows | Read-only / reversible |
| `system_control` | Volume, mute, brightness, dark mode, Wi-Fi/Bluetooth on or off, lock screen | Prompt every time |
| `clipboard` | Read, write | Read = prompt once per session |
| `notify` | Desktop notification, timer, alarm, reminder | No prompt |
| `screen` | Screenshot (for vision models), read text on screen | Prompt once per session |
| `open_path` | Open a file, folder or URL in its default app | No prompt for files, prompt for executables |

- Implementation candidates: `pywinauto`/`pycaw`/Win32 APIs on Windows, AppleScript/`osascript` on macOS, `wmctrl`/`xdotool`/D-Bus on Linux. Put them in a `desktop-control` optional extra.
- Full mouse-and-keyboard UI automation is deliberately **out of scope** for this phase: it's fragile and risky. Revisit after the structured tools are in.

**Done when:** "turn the volume down to 30 percent and open my Downloads folder" works on Windows; each tool has unit tests with the OS layer mocked; risky actions go through phase 3 approvals.

### Phase 5: hands-free voice loop

**Goal:** talk to Locus without touching the keyboard.

- **Activation:** a global hotkey (Tauri global shortcut) that opens the overlay and starts listening; an optional local wake word (for example openWakeWord) behind a setting, off by default.
- **End-of-speech detection:** voice activity detection (Silero VAD or WebRTC VAD) so recording stops when the user stops talking.
- **Spoken replies:** in voice mode, speak the final answer with Kokoro (local) by default. Speak short status lines for long tasks ("Moving 12 files…").
- **Interruption:** when the user starts talking during playback, stop playback and start listening.
- **Voice approvals:** "yes", "no" and "cancel" answer an approval prompt, but irreversible actions (delete, send, purchase) also need a click or a typed confirmation.
- Show the transcript as editable text before sending, with a setting to auto-send.

**Done when:** from the hotkey, "what's on my calendar today?" is answered aloud with no clicks; interrupting stops playback within ~300 ms; everything runs offline with faster-whisper + Kokoro.

### Phase 6: developer mode

**Goal:** a strong local coding agent built on the existing tools.

- A `developer` preset: `native_openhands` or `orchestrator` with `shell_exec`, `apply_patch`, `git_tool`, `file_read`/`file_write`, `code_interpreter_docker`, `http_request`, `db_query`, MCP.
- **Project scope:** the user picks a project folder; file and shell tools are limited to it (`file_policy.py`, `mount_security.py`).
- **Diff review:** show `apply_patch` changes as a diff to accept or reject before writing.
- **Test and fix loop:** run the project's test command, read failures, patch, re-run, up to a turn limit.
- **Command allowlist:** safe commands (`git status`, test runners, linters) run without prompts; anything else asks.
- **Git hygiene:** work on a new branch, write commit messages, never push without approval.

**Done when:** on a sample repo with a failing test, "fix the failing test" produces a reviewed diff, a passing test run and a local commit on a new branch.

## 5. Order and dependencies

```
Phase 1 ──► Phase 2 ──► Phase 3 ──┬──► Phase 4 (desktop tools)
                                  ├──► Phase 5 (voice loop)
                                  └──► Phase 6 (developer mode)
```

Phases 4–6 can run in parallel once phase 3 is merged, since they touch separate files.

## 6. Cross-cutting requirements

- **Privacy:** no new network calls by default. Wake word, speech to text, text to speech and every new tool run locally.
- **Safety:** every tool declares a risk level; irreversible and outward actions always prompt; all tool calls go to the audit log and traces.
- **Prompt injection:** tool output (web pages, files, email) is treated as data; keep `injection_scanner.py` on that output and never let it approve actions.
- **Small machines:** on machines that only fit models under ~4B, agent mode still works but warns that results may be unreliable, and suggests a larger model or a cloud key.
- **Tests:** each phase adds unit tests and at least one end-to-end test with a scripted fake engine, so CI doesn't need a real model.
- **Docs:** user guide pages for agent mode, voice mode and developer mode; update the README "What Locus can do" section.

## 7. Open questions

1. Should agent mode become the default for new desktop installs, or stay opt-in for the first release?
2. Which minimum model should agent mode recommend on 8 GB machines (`qwen3.5:4b` vs a tool-tuned alternative)? Needs a small benchmark with `locus bench`.
3. Wake word: ship it in the first voice release or after?
4. Should approvals be shareable across channels (approve a desktop action from Telegram), reusing the proactive agent's approval routing?
