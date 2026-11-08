import { useState, useRef, useCallback, useEffect } from 'react';
import { Send, Square, Paperclip, Search, Globe, Bot, FolderCode, X } from 'lucide-react';
import { toast } from 'sonner';
import { useAppStore, generateId } from '../../lib/store';
import { streamChat, streamResearch } from '../../lib/sse';
import { fetchSavings, getBase, isTauri, stopAgentRun } from '../../lib/api';
import { listConnectors, getSyncStatus } from '../../lib/connectors-api';
import { serializeToolCallArguments } from '../../lib/tool-call';
import { stoppedSummary } from '../../lib/agent-stop';
import {
  engineFromCompletionChunk,
  resolveChatEngine,
} from '../../lib/chat-telemetry';
import { MicButton } from './MicButton';
import { AgentModelHint } from './AgentModelHint';
import { AttachmentChip } from './AttachmentChip';
import { useSpeech } from '../../hooks/useSpeech';
import { useHandsFree } from '../../hooks/useHandsFree';
import {
  apiAttachmentFields,
  deletePayloads,
  MAX_FILE_BYTES,
  MAX_FILES_PER_MESSAGE,
  readAttachments,
  savePayload,
} from '../../lib/attachments';
import type {
  AttachmentMeta,
  ChatMessage,
  MessageTelemetry,
  ResearchSearchTrace,
  ResearchSource,
  TokenUsage,
  ToolCallInfo,
} from '../../types';

/** A file in the input box: being read by the server, ready, or failed. */
interface PendingAttachment {
  key: string;
  name: string;
  status: 'reading' | 'ready' | 'error';
  meta?: AttachmentMeta;
  error?: string;
}

// While Deep Research is toggled on, poll connected sources for sync
// progress so we can surface "Searching over N items — sync in progress"
// next to the toggle. Polling is gated on `enabled` so toggling DR off
// stops the network chatter immediately.
function useResearchCorpusSync(enabled: boolean): {
  syncing: boolean;
  itemsSynced: number;
} {
  const [state, setState] = useState({ syncing: false, itemsSynced: 0 });

  useEffect(() => {
    if (!enabled) {
      setState({ syncing: false, itemsSynced: 0 });
      return;
    }
    let cancelled = false;

    const poll = async () => {
      try {
        const list = await listConnectors();
        const connected = list.filter((c) => c.connected);
        if (connected.length === 0) {
          if (!cancelled) setState({ syncing: false, itemsSynced: 0 });
          return;
        }
        const results = await Promise.all(
          connected.map(async (c) => {
            try {
              return await getSyncStatus(c.connector_id);
            } catch {
              return null;
            }
          }),
        );
        let syncing = false;
        let itemsSynced = 0;
        for (const r of results) {
          if (!r) continue;
          if (r.state === 'syncing') syncing = true;
          itemsSynced += r.items_synced ?? 0;
        }
        if (!cancelled) setState({ syncing, itemsSynced });
      } catch {
        // Network blip — leave previous state intact.
      }
    };

    poll();
    const interval = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [enabled]);

  return state;
}

export function InputArea() {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Agent mode run being streamed, so Stop can end it on the server too.
  const agentRunRef = useRef<string | null>(null);
  // Set when the user stops an Agent mode run (not a model switch).
  const stoppedByUserRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const activeId = useAppStore((s) => s.activeId);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const streamState = useAppStore((s) => s.streamState);
  const messages = useAppStore((s) => s.messages);
  const speechEnabled = useAppStore((s) => s.settings.speechEnabled);
  const maxTokens = useAppStore((s) => s.settings.maxTokens);
  const temperature = useAppStore((s) => s.settings.temperature);
  const createConversation = useAppStore((s) => s.createConversation);
  const addMessage = useAppStore((s) => s.addMessage);
  const updateLastAssistant = useAppStore((s) => s.updateLastAssistant);
  const setStreamState = useAppStore((s) => s.setStreamState);
  const resetStream = useAppStore((s) => s.resetStream);
  const modelLoading = useAppStore((s) => s.modelLoading);
  const deepResearch = useAppStore((s) => s.deepResearch);
  const setDeepResearch = useAppStore((s) => s.setDeepResearch);
  const webSearch = useAppStore((s) => s.webSearch);
  const setWebSearch = useAppStore((s) => s.setWebSearch);
  const setLastAssistantWebSearch = useAppStore((s) => s.setLastAssistantWebSearch);
  const agentMode = useAppStore((s) => s.agentMode);
  const setAgentMode = useAppStore((s) => s.setAgentMode);
  const projectDir = useAppStore((s) => s.projectDir);
  const setProjectDir = useAppStore((s) => s.setProjectDir);
  const corpusSync = useResearchCorpusSync(deepResearch);

  const [pending, setPending] = useState<PendingAttachment[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const readyAttachments = pending.filter((p) => p.status === 'ready' && p.meta);
  const attachmentsReading = pending.some((p) => p.status === 'reading');

  const addFiles = useCallback(async (incoming: File[]) => {
    let files = incoming;
    if (files.length === 0) return;
    const room = MAX_FILES_PER_MESSAGE - pending.filter((p) => p.status !== 'error').length;
    if (room <= 0) {
      toast.error(`Attach at most ${MAX_FILES_PER_MESSAGE} files per message.`);
      return;
    }
    if (files.length > room) {
      toast.error(`Only the first ${room} file(s) were added (${MAX_FILES_PER_MESSAGE} per message).`);
      files = files.slice(0, room);
    }
    for (const f of files.filter((f) => f.size > MAX_FILE_BYTES)) {
      toast.error(`${f.name} is larger than 25 MB.`);
    }
    files = files.filter((f) => f.size <= MAX_FILE_BYTES);
    if (files.length === 0) return;

    const keys = files.map(() => generateId());
    setPending((prev) => [
      ...prev,
      ...files.map((f, i) => ({ key: keys[i], name: f.name, status: 'reading' as const })),
    ]);
    try {
      const results = await readAttachments(files);
      await Promise.all(results.map((res) => savePayload(res.meta.id, res.payload)));
      setPending((prev) =>
        prev.map((p) => {
          const i = keys.indexOf(p.key);
          return i === -1 ? p : { ...p, status: 'ready', meta: results[i]?.meta };
        }),
      );
    } catch (err: any) {
      const message = err?.message || 'Could not read the file.';
      toast.error(message);
      setPending((prev) =>
        prev.map((p) => (keys.includes(p.key) ? { ...p, status: 'error', error: message } : p)),
      );
    }
  }, [pending]);

  const removePending = useCallback((key: string) => {
    setPending((prev) => {
      const item = prev.find((p) => p.key === key);
      if (item?.meta) void deletePayloads([item.meta.id]);
      return prev.filter((p) => p.key !== key);
    });
  }, []);

  // Web search and Deep Research are separate modes; turning one on turns
  // the other off.
  const toggleWebSearch = () => {
    setWebSearch(!webSearch);
    if (!webSearch && deepResearch) setDeepResearch(false);
  };
  const toggleDeepResearch = () => {
    setDeepResearch(!deepResearch);
    if (!deepResearch && webSearch) setWebSearch(false);
    if (!deepResearch && agentMode) setAgentMode(false);
  };
  // Developer mode: Agent mode inside one project folder.
  const pickProject = async () => {
    let dir: string | null = null;
    if (isTauri()) {
      try {
        const { open } = await import('@tauri-apps/plugin-dialog');
        const picked = await open({ directory: true, title: 'Choose a project folder' });
        dir = typeof picked === 'string' ? picked : null;
      } catch {
        dir = null;
      }
    } else {
      dir = window.prompt('Full path of the project folder', projectDir ?? '')?.trim() || null;
    }
    if (!dir) return;
    setProjectDir(dir);
    if (!agentMode) setAgentMode(true);
    if (deepResearch) setDeepResearch(false);
  };

  // Agent mode and Deep Research both decide how to answer, so only one is on.
  const toggleAgentMode = () => {
    setAgentMode(!agentMode);
    if (!agentMode && deepResearch) setDeepResearch(false);
  };
  const isCurrentChatStreaming = streamState.isStreaming && streamState.conversationId === activeId;

  const {
    state: speechState,
    error: speechError,
    available: speechAvailable,
    startRecording,
    stopRecording,
    cancelRecording,
  } = useSpeech();

  // Hands-free: the transcript goes out through the prompt queue, which
  // sends it as soon as no reply is streaming.
  const handsFree = useAppStore((s) => s.settings.handsFree);
  useHandsFree({
    enabled: handsFree,
    available: speechAvailable,
    state: speechState,
    startRecording,
    stopRecording,
    cancelRecording,
    send: (text) => useAppStore.getState().queuePrompt(text),
  });

  // Abort in-flight stream when the user switches models mid-generation.
  // This prevents errors from trying to continue a stream with a stale model.
  const prevModelRef = useRef(selectedModel);
  useEffect(() => {
    if (prevModelRef.current !== selectedModel && streamState.isStreaming) {
      abortRef.current?.abort();
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      resetStream();
      abortRef.current = null;
    }
    prevModelRef.current = selectedModel;
  }, [selectedModel, streamState.isStreaming, resetStream]);

  const micDisabled = !speechEnabled || !speechAvailable || streamState.isStreaming;
  const micReason: 'not-enabled' | 'no-backend' | 'streaming' | undefined =
    !speechEnabled ? 'not-enabled'
    : !speechAvailable ? 'no-backend'
    : streamState.isStreaming ? 'streaming'
    : undefined;

  useEffect(() => {
    if (speechError) {
      toast.error(speechError, { duration: 8000 });
    }
  }, [speechError]);

  const handleMicClick = useCallback(async () => {
    if (speechState === 'recording') {
      try {
        const text = await stopRecording();
        if (text) {
          setInput((prev) => (prev ? prev + ' ' + text : text));
        }
      } catch {
        // Error is captured in useSpeech
      }
    } else {
      await startRecording();
    }
  }, [speechState, startRecording, stopRecording]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }, [input]);

  const stopStreaming = useCallback(() => {
    if (agentRunRef.current) {
      void stopAgentRun(agentRunRef.current).catch(() => {});
      agentRunRef.current = null;
      stoppedByUserRef.current = true;
    }
    abortRef.current?.abort();
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    resetStream();
  }, [resetStream]);

  // `prompt` sends that text instead of the input box (Continue does this).
  const sendMessage = useCallback(async (prompt?: unknown) => {
    const fromPrompt = typeof prompt === 'string';
    const content = (fromPrompt ? prompt : input).trim();
    const attachments = readyAttachments.map((p) => p.meta!);
    if ((!content && attachments.length === 0) || streamState.isStreaming) return;
    if (attachmentsReading) {
      toast.error('Wait for the attached files to finish reading.');
      return;
    }
    if (!selectedModel) {
      toast.error('Pick a model first (⌘K)');
      return;
    }
    if (deepResearch && attachments.length > 0) {
      toast.error("Deep Research can't use attached files. Turn it off to ask about them.");
      return;
    }
    const searchWeb = webSearch && !deepResearch;

    if (!fromPrompt) setInput('');
    setPending([]);

    let convId = activeId;
    if (!convId) {
      convId = createConversation(selectedModel);
    }

    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content,
      timestamp: Date.now(),
      ...(attachments.length > 0 ? { attachments } : {}),
    };
    addMessage(convId, userMsg);

    // Build API messages before adding assistant placeholder. Attachment
    // content is read back from IndexedDB for every message that has some.
    const currentMessages = useAppStore.getState().messages;
    const apiMessages = await Promise.all(
      currentMessages.map(async (m) => ({
        role: m.role,
        content: m.content,
        ...(m.role === 'user' ? await apiAttachmentFields(m.attachments) : {}),
      })),
    );
    // The agent gets attached files, images and web results too.
    const useAgent = agentMode && !deepResearch;

    const assistantMsg: ChatMessage = {
      id: generateId(),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      isResearch: deepResearch || undefined,
    };
    addMessage(convId, assistantMsg);

    // Start streaming
    const startTime = Date.now();
    const timer = setInterval(() => {
      setStreamState({ elapsedMs: Date.now() - startTime });
    }, 100);
    timerRef.current = timer;

    const controller = new AbortController();
    abortRef.current = controller;
    agentRunRef.current = null;
    stoppedByUserRef.current = false;

    let accumulatedContent = '';
    let usage: TokenUsage | undefined;
    let complexity: { score: number; tier: string; suggested_max_tokens: number } | undefined;
    let routedEngine: string | undefined;
    const toolCalls: ToolCallInfo[] = [];
    const researchTraces: ResearchSearchTrace[] = [];
    const researchSourcesByRef = new Map<number, ResearchSource>();
    const flushSources = () =>
      Array.from(researchSourcesByRef.values()).sort((a, b) => a.ref - b.ref);
    let lastFlush = 0;
    let ttftMs: number | undefined;

    setStreamState({
      conversationId: convId,
      isStreaming: true,
      phase: deepResearch ? 'Researching...' : searchWeb ? 'Searching the web...' : 'Generating...',
      elapsedMs: 0,
      activeToolCalls: [],
      content: '',
    });
    useAppStore.getState().addLogEntry({
      timestamp: Date.now(),
      level: 'info',
      category: 'chat',
      message: deepResearch
        ? `Research: "${content.slice(0, 80)}${content.length > 80 ? '...' : ''}"`
        : `Request: "${content.slice(0, 80)}${content.length > 80 ? '...' : ''}" → ${selectedModel}`,
    });

    try {
      if (deepResearch) {
        for await (const ev of streamResearch(
          content,
          selectedModel,
          controller.signal,
        )) {
          if (ev.type === 'search_call') {
            const trace: ResearchSearchTrace = {
              id: generateId(),
              query: ev.arguments?.query ?? '',
              person: ev.arguments?.person,
              timeRange: ev.arguments?.time_range,
              status: 'pending',
            };
            researchTraces.push(trace);
            setStreamState({ phase: `Searching: ${trace.query}` });
            updateLastAssistant(
              convId,
              accumulatedContent,
              undefined,
              undefined,
              undefined,
              undefined,
              [...researchTraces],
              flushSources(),
            );
            useAppStore.getState().addLogEntry({
              timestamp: Date.now(),
              level: 'info',
              category: 'tool',
              message: `Search: "${trace.query}"${trace.person ? ` (person: ${trace.person})` : ''}`,
            });
          } else if (ev.type === 'search_result') {
            const pending = [...researchTraces].reverse().find((t) => t.status === 'pending');
            if (pending) {
              pending.status = 'complete';
              pending.numHits = ev.num_hits;
              pending.topTitles = ev.top_titles;
            }
            if (ev.sources) {
              for (const src of ev.sources) {
                if (src && typeof src.ref === 'number' && !researchSourcesByRef.has(src.ref)) {
                  researchSourcesByRef.set(src.ref, src);
                }
              }
            }
            updateLastAssistant(
              convId,
              accumulatedContent,
              undefined,
              undefined,
              undefined,
              undefined,
              [...researchTraces],
              flushSources(),
            );
          } else if (ev.type === 'synthesis') {
            if (!ttftMs) ttftMs = Date.now() - startTime;
            accumulatedContent += ev.text;
            setStreamState({ content: accumulatedContent, phase: '' });
            const now = Date.now();
            if (now - lastFlush >= 80) {
              updateLastAssistant(
                convId,
                accumulatedContent,
                undefined,
                undefined,
                undefined,
                undefined,
                [...researchTraces],
                flushSources(),
              );
              lastFlush = now;
            }
          } else if (ev.type === 'system_metrics') {
            // Live GPU sample — feed straight to the System panel so Power
            // (W) and Energy (kJ) tick up in real time as the agent runs.
            useAppStore.getState().setLiveEnergy({
              power_w: ev.power_w,
              energy_j: ev.energy_j,
              duration_s: ev.duration_s,
            });
          } else if (ev.type === 'error') {
            // Backend setup/worker failure (Ollama down, planner model
            // missing, KnowledgeStore locked, etc.). Without surfacing the
            // message, the user sees only the generic "No response was
            // generated" fallback and has no way to self-diagnose.
            const msg = ev.message || 'Research failed (no detail provided)';
            accumulatedContent = accumulatedContent
              ? `${accumulatedContent}\n\n**Research stopped:** ${msg}`
              : `**Research failed:** ${msg}`;
            setStreamState({ content: accumulatedContent, phase: '' });
            useAppStore.getState().addLogEntry({
              timestamp: Date.now(),
              level: 'error',
              category: 'chat',
              message: `Deep Research error: ${msg}`,
            });
            toast.error(msg, { duration: 8000 });
          } else if (ev.type === 'done') {
            if (ev.usage) {
              usage = {
                prompt_tokens: ev.usage.prompt_tokens ?? 0,
                completion_tokens: ev.usage.completion_tokens ?? 0,
                total_tokens:
                  ev.usage.total_tokens ??
                  (ev.usage.prompt_tokens ?? 0) +
                    (ev.usage.completion_tokens ?? 0),
              };
              // Optimistically roll this research turn into the session
              // counters so the Session panel updates the moment the
              // stream finishes, regardless of how /v1/savings aggregates
              // research telemetry server-side.
              useAppStore.getState().incrementSavings(usage);
            }
            // Hold the final live numbers visible for a beat so the panel
            // doesn't flash to 0 between the SSE close and the next
            // /v1/telemetry/energy poll picking up the persisted record.
            window.setTimeout(() => {
              useAppStore.getState().setLiveEnergy(null);
            }, 1500);
            break;
          }
        }
      } else {
      for await (const sseEvent of streamChat(
        {
          model: selectedModel,
          messages: apiMessages,
          stream: true,
          temperature,
          max_tokens: maxTokens,
          ...(searchWeb ? { web_search: true } : {}),
          ...(useAgent
            ? projectDir
              ? { mode: 'developer' as const, project_dir: projectDir }
              : { mode: 'agent' as const }
            : {}),
        },
        controller.signal,
      )) {
        const eventName = sseEvent.event;

        if (eventName === 'web_search') {
          try {
            const data = JSON.parse(sseEvent.data);
            const sources: ResearchSource[] = (data.sources ?? []).map((src: any) => ({
              ref: src.ref,
              title: src.title,
              url: src.url,
            }));
            setLastAssistantWebSearch(
              convId,
              { query: data.query, engine: data.engine || undefined, error: data.error || undefined },
              sources,
            );
            setStreamState({
              phase: data.error ? 'Web search failed, answering without it...' : 'Generating...',
            });
            useAppStore.getState().addLogEntry({
              timestamp: Date.now(),
              level: data.error ? 'warn' : 'info',
              category: 'chat',
              message: data.error
                ? `Web search failed: ${data.error}`
                : `Web search found ${sources.length} source(s)`,
            });
          } catch {}
        } else if (eventName === 'agent_run') {
          try {
            agentRunRef.current = JSON.parse(sseEvent.data).run_id ?? null;
          } catch {}
        } else if (eventName === 'approval_required') {
          try {
            const data = JSON.parse(sseEvent.data);
            toolCalls.push({
              id: generateId(),
              tool: data.tool,
              arguments: serializeToolCallArguments(data.arguments),
              status: 'awaiting_approval',
              approvalId: data.id,
              risk: data.risk,
              canAlways: Boolean(data.can_always),
              preview: data.preview || undefined,
            });
            setStreamState({
              phase: 'Waiting for your approval...',
              activeToolCalls: [...toolCalls],
            });
            updateLastAssistant(convId, accumulatedContent, [...toolCalls]);
          } catch {}
        } else if (eventName === 'approval_resolved') {
          try {
            const data = JSON.parse(sseEvent.data);
            const tc = toolCalls.find((t) => t.approvalId === data.id);
            if (tc) {
              tc.status = data.approved ? 'approved' : 'denied';
              if (data.timed_out) tc.result = 'No answer in time, so the agent skipped this step.';
            }
            setStreamState({
              phase: data.approved ? `Calling ${data.tool}...` : 'Agent thinking...',
              activeToolCalls: [...toolCalls],
            });
            updateLastAssistant(convId, accumulatedContent, [...toolCalls]);
          } catch {}
        } else if (eventName === 'agent_turn_start') {
          setStreamState({ phase: 'Agent thinking...' });
        } else if (eventName === 'inference_start') {
          setStreamState({ phase: 'Generating...' });
          useAppStore.getState().addLogEntry({
            timestamp: Date.now(), level: 'info', category: 'chat',
            message: `Generating with ${selectedModel}...`,
          });
        } else if (eventName === 'tool_call_start') {
          try {
            const data = JSON.parse(sseEvent.data);
            // An approved call is already on screen; it starts running now.
            const approved = toolCalls.find((t) => t.tool === data.tool && t.status === 'approved');
            if (approved) {
              approved.status = 'running';
            } else {
              toolCalls.push({
                id: generateId(),
                tool: data.tool,
                arguments: serializeToolCallArguments(data.arguments),
                status: 'running',
              });
            }
            setStreamState({
              phase: data.tool === 'task_plan' ? 'Planning...' : `Calling ${data.tool}...`,
              activeToolCalls: [...toolCalls],
            });
            updateLastAssistant(convId, accumulatedContent, [...toolCalls]);
            useAppStore.getState().addLogEntry({
              timestamp: Date.now(), level: 'info', category: 'tool',
              message: `Calling ${data.tool}(${serializeToolCallArguments(data.arguments)})`,
            });
          } catch {}
        } else if (eventName === 'tool_call_end') {
          try {
            const data = JSON.parse(sseEvent.data);
            const tc = toolCalls.find(
              (t) => t.tool === data.tool && t.status === 'running',
            );
            if (tc) {
              tc.status = data.success ? 'success' : 'error';
              tc.latency = data.latency;
              tc.result = data.result;
              if (data.metadata?.undo_id) tc.undoId = data.metadata.undo_id;
            }
            setStreamState({
              phase: 'Generating...',
              activeToolCalls: [...toolCalls],
            });
            updateLastAssistant(convId, accumulatedContent, [...toolCalls]);
          } catch {}
        } else {
          try {
            const data = JSON.parse(sseEvent.data);
            const delta = data.choices?.[0]?.delta;
            if (data.usage) usage = data.usage;
            if (data.complexity) complexity = data.complexity;
            routedEngine = engineFromCompletionChunk(data) ?? routedEngine;
            if (delta?.content) {
              if (!ttftMs) ttftMs = Date.now() - startTime;
              accumulatedContent += delta.content;
              setStreamState({ content: accumulatedContent, phase: '' });

              const now = Date.now();
              if (now - lastFlush >= 80) {
                updateLastAssistant(
                  convId,
                  accumulatedContent,
                  toolCalls.length > 0 ? [...toolCalls] : undefined,
                );
                lastFlush = now;
              }
            }
            if (data.choices?.[0]?.finish_reason === 'stop') break;
          } catch {}
        }
      }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        // User cancelled or model switch — keep whatever was accumulated
        if (!accumulatedContent) accumulatedContent = '(Generation stopped)';
      } else {
        const errMsg = err?.message || String(err);
        accumulatedContent =
          accumulatedContent || `Error: ${errMsg}`;
        useAppStore.getState().addLogEntry({
          timestamp: Date.now(), level: 'error', category: 'chat',
          message: `Stream error: ${errMsg}`,
        });
      }
      // If we tore out mid-research, make sure the live System panel
      // numbers don't get stuck on the last sample.
      useAppStore.getState().setLiveEnergy(null);
    } finally {
      agentRunRef.current = null;
      // A stopped run leaves no step waiting for an answer.
      for (const tc of toolCalls) {
        if (tc.status === 'awaiting_approval' || tc.status === 'approved') tc.status = 'denied';
      }
      const stoppedAgent = useAgent && stoppedByUserRef.current;
      if (stoppedAgent) {
        accumulatedContent = stoppedSummary(
          toolCalls,
          accumulatedContent === '(Generation stopped)' ? '' : accumulatedContent,
        );
      }
      if (!accumulatedContent) {
        accumulatedContent = 'No response was generated. Please try again.';
      }
      const totalMs = Date.now() - startTime;
      const appState = useAppStore.getState();
      const selectedOwner = appState.models.find((m) => m.id === selectedModel)?.owned_by;
      const engineLabel = resolveChatEngine({
        routedEngine,
        serverEngine: appState.serverInfo?.engine,
        selectedModel,
        selectedOwner,
      });
      const telemetry: MessageTelemetry = {
        engine: engineLabel,
        model_id: selectedModel,
        total_ms: totalMs,
        ttft_ms: ttftMs,
        tokens_per_sec: usage?.completion_tokens
          ? usage.completion_tokens / (totalMs / 1000)
          : undefined,
        complexity_score: complexity?.score,
        complexity_tier: complexity?.tier,
        suggested_max_tokens: complexity?.suggested_max_tokens,
      };
      // Check if the response has digest audio available
      let audioMeta: { url: string } | undefined;
      try {
        const digestRes = await fetch(`${getBase()}/api/digest`);
        if (digestRes.ok) {
          const digest = await digestRes.json();
          if (digest.audio_available) {
            audioMeta = { url: `${getBase()}/api/digest/audio` };
          }
        }
      } catch {
        // Not a digest response or server unavailable — skip
      }

      updateLastAssistant(
        convId,
        accumulatedContent,
        toolCalls.length > 0 ? toolCalls : undefined,
        usage,
        telemetry,
        audioMeta,
        researchTraces.length > 0 ? researchTraces : undefined,
        researchSourcesByRef.size > 0 ? flushSources() : undefined,
      );
      if (stoppedAgent) useAppStore.getState().markLastAssistantStopped(convId, true);
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      resetStream();
      useAppStore.getState().addLogEntry({
        timestamp: Date.now(), level: 'info', category: 'chat',
        message: `Response: ${accumulatedContent.length} chars`,
      });
      abortRef.current = null;

      // Research path updates session counters optimistically from the
      // `done` event's usage payload — re-fetching here would overwrite
      // it with a potentially stale snapshot if the server's research
      // telemetry hasn't been merged into /v1/savings yet.
      if (!deepResearch) {
        fetchSavings()
          .then((data) => useAppStore.getState().setSavings(data))
          .catch(() => {});
      }
    }
  }, [
    input,
    activeId,
    selectedModel,
    streamState.isStreaming,
    createConversation,
    addMessage,
    updateLastAssistant,
    setStreamState,
    resetStream,
    deepResearch,
    temperature,
    maxTokens,
    readyAttachments,
    attachmentsReading,
    webSearch,
    setLastAssistantWebSearch,
    agentMode,
    projectDir,
  ]);

  const queuedPrompt = useAppStore((s) => s.queuedPrompt);
  useEffect(() => {
    if (!queuedPrompt || streamState.isStreaming) return;
    useAppStore.getState().queuePrompt(null);
    void sendMessage(queuedPrompt);
  }, [queuedPrompt, streamState.isStreaming, sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="px-4 pb-4 pt-2" style={{ maxWidth: 'var(--chat-max-width)', margin: '0 auto', width: '100%' }}>
      <div className="mb-2 flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggleWebSearch}
            disabled={streamState.isStreaming}
            aria-pressed={webSearch}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs transition-colors cursor-pointer disabled:cursor-default disabled:opacity-50"
            style={{
              background: webSearch ? 'var(--color-accent-subtle)' : 'transparent',
              border: `1px solid ${webSearch ? 'var(--color-accent)' : 'var(--color-border)'}`,
              color: webSearch ? 'var(--color-accent)' : 'var(--color-text-tertiary)',
            }}
            title={
              webSearch
                ? 'Web search: on. Your message is sent to a search engine before Locus answers.'
                : 'Web search: off. Turn on to look things up online.'
            }
          >
            <Globe size={12} />
            Web search
          </button>
          <button
            type="button"
            onClick={toggleDeepResearch}
            disabled={streamState.isStreaming}
            aria-pressed={deepResearch}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs transition-colors cursor-pointer disabled:cursor-default disabled:opacity-50"
            style={{
              background: deepResearch ? 'var(--color-accent-subtle)' : 'transparent',
              border: `1px solid ${deepResearch ? 'var(--color-accent)' : 'var(--color-border)'}`,
              color: deepResearch ? 'var(--color-accent)' : 'var(--color-text-tertiary)',
            }}
            title={deepResearch ? 'Deep Research: on' : 'Deep Research: off'}
          >
            <Search size={12} />
            Deep Research
          </button>
          <button
            type="button"
            onClick={toggleAgentMode}
            disabled={streamState.isStreaming}
            aria-pressed={agentMode}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs transition-colors cursor-pointer disabled:cursor-default disabled:opacity-50"
            style={{
              background: agentMode ? 'var(--color-accent-subtle)' : 'transparent',
              border: `1px solid ${agentMode ? 'var(--color-accent)' : 'var(--color-border)'}`,
              color: agentMode ? 'var(--color-accent)' : 'var(--color-text-tertiary)',
            }}
            title={
              agentMode
                ? 'Agent: on. Locus can use tools, like reading your files, to do what you ask.'
                : 'Agent: off. Turn on to let Locus use tools to do tasks.'
            }
          >
            <Bot size={12} />
            Agent
          </button>
          <div
            className="inline-flex items-center rounded-full text-xs"
            style={{
              background: projectDir && agentMode ? 'var(--color-accent-subtle)' : 'transparent',
              border: `1px solid ${projectDir && agentMode ? 'var(--color-accent)' : 'var(--color-border)'}`,
              color: projectDir && agentMode ? 'var(--color-accent)' : 'var(--color-text-tertiary)',
              opacity: streamState.isStreaming ? 0.5 : 1,
            }}
          >
            <button
              type="button"
              onClick={pickProject}
              disabled={streamState.isStreaming}
              className="inline-flex items-center gap-1.5 pl-2.5 py-1 cursor-pointer disabled:cursor-default"
              style={{ paddingRight: projectDir ? 4 : 10 }}
              title={
                projectDir
                  ? `Developer mode in ${projectDir}. Click to choose another folder.`
                  : 'Developer mode: let Agent mode work on code in one project folder.'
              }
            >
              <FolderCode size={12} />
              {projectDir ? projectDir.split(/[\\/]/).filter(Boolean).pop() : 'Project'}
            </button>
            {projectDir && (
              <button
                type="button"
                onClick={() => setProjectDir(null)}
                disabled={streamState.isStreaming}
                className="pr-2 py-1 cursor-pointer disabled:cursor-default"
                aria-label="Stop using the project folder"
                title="Stop using the project folder"
              >
                <X size={11} />
              </button>
            )}
          </div>
        </div>
        {agentMode && selectedModel && <AgentModelHint selectedModel={selectedModel} />}
        {deepResearch && corpusSync.syncing && corpusSync.itemsSynced > 0 && (
          <div
            className="text-[11px] leading-snug"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            Searching over{' '}
            <span key={corpusSync.itemsSynced} className="sync-bump" style={{ color: 'var(--color-text-secondary)' }}>
              {corpusSync.itemsSynced.toLocaleString()}
            </span>{' '}
            items — sync in progress, results will improve as more data is indexed.
          </div>
        )}
      </div>
      <div
        className="rounded-2xl px-4 py-3 transition-shadow"
        style={{
          background: 'var(--color-input-bg)',
          border: `1px ${dragging ? 'dashed' : 'solid'} ${dragging ? 'var(--color-accent)' : 'var(--color-input-border)'}`,
          boxShadow: 'var(--shadow-sm)',
        }}
        onDragOver={(e) => {
          if (!e.dataTransfer.types.includes('Files')) return;
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
        }}
        onDrop={(e) => {
          if (!e.dataTransfer.files.length) return;
          e.preventDefault();
          setDragging(false);
          void addFiles(Array.from(e.dataTransfer.files));
        }}
      >
        {pending.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {pending.map((p) => (
              <AttachmentChip
                key={p.key}
                name={p.name}
                meta={p.meta}
                status={p.status}
                error={p.error}
                onRemove={() => removePending(p.key)}
              />
            ))}
          </div>
        )}
        <div className="flex items-center gap-2">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          onChange={(e) => {
            void addFiles(Array.from(e.target.files ?? []));
            e.target.value = '';
          }}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={streamState.isStreaming || modelLoading}
          title="Attach files or images (or drop them here)"
          aria-label="Attach files"
          className="p-1.5 -ml-1.5 rounded-lg transition-colors shrink-0 cursor-pointer disabled:opacity-30 disabled:cursor-default"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          <Paperclip size={16} />
        </button>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={(e) => {
            const files = Array.from(e.clipboardData.files);
            if (files.length === 0) return;
            // Pasting a screenshot or copied files attaches them; any text
            // on the clipboard is still pasted.
            if (!e.clipboardData.getData('text')) e.preventDefault();
            void addFiles(files);
          }}
          placeholder={selectedModel ? 'Message Locus...' : 'Pick a model first (⌘K)...'}
          rows={1}
          className="flex-1 bg-transparent outline-none resize-none text-sm leading-relaxed"
          style={{ color: 'var(--color-text)', maxHeight: '200px' }}
          disabled={streamState.isStreaming || modelLoading}
        />
        {isCurrentChatStreaming ? (
          <button
            onClick={stopStreaming}
            className="p-2 rounded-xl transition-colors shrink-0 cursor-pointer"
            style={{ background: 'var(--color-error)', color: 'var(--color-on-accent)' }}
            title="Stop generating"
          >
            <Square size={16} />
          </button>
        ) : (
          <div className="flex items-center gap-1">
            <MicButton
              state={speechState}
              onClick={handleMicClick}
              disabled={micDisabled}
              reason={micReason}
            />
            <button
              onClick={sendMessage}
              disabled={
                streamState.isStreaming ||
                (!input.trim() && readyAttachments.length === 0) ||
                attachmentsReading ||
                modelLoading ||
                !selectedModel
              }
              title={
                !selectedModel
                  ? 'Pick a model first (⌘K)'
                  : attachmentsReading
                    ? 'Reading attached files...'
                    : 'Send message'
              }
              className="p-2 rounded-xl transition-colors shrink-0 cursor-pointer disabled:opacity-30 disabled:cursor-default"
              style={{
                background: input.trim() || readyAttachments.length > 0 ? 'var(--color-accent)' : 'var(--color-bg-tertiary)',
                color: input.trim() || readyAttachments.length > 0 ? 'white' : 'var(--color-text-tertiary)',
              }}
            >
              <Send size={16} />
            </button>
          </div>
        )}
        </div>
      </div>
      <div className="flex items-center justify-center mt-2 text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
        <span>
          <kbd className="font-mono">Enter</kbd> to send &middot;{' '}
          <kbd className="font-mono">Shift+Enter</kbd> for new line
        </span>
      </div>
    </div>
  );
}
