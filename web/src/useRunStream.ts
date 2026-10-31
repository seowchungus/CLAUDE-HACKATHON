import { useEffect, useReducer } from "react";
import { api } from "./api";
import {
  EVENT_TYPES,
  type AgentMessage,
  type AgentRole,
  type ApprovedData,
  type AwaitingApprovalData,
  type CheckReport,
  type ConsensusData,
  type CounterCheckedData,
  type Envelope,
  type FallbackData,
  type FallbackResult,
  type Option,
  type RoundStartedData,
  type RunEndedData,
  type RunStartedData,
  type TentativeData,
  type VetoData,
} from "./types";

export type Card =
  | { kind: "thinking"; round: number; agent: AgentRole; seq: number }
  | { kind: "position"; round: number; agent: AgentRole; seq: number; msg: AgentMessage }
  | { kind: "counter"; round: number; agent: AgentRole; seq: number; cc: CounterCheckedData };

export interface RunState {
  runId: string | null;
  lastSeq: number;
  connected: boolean;
  started: RunStartedData | null;
  options: Option[];
  checks: Record<string, CheckReport>;
  fallbackShadow: FallbackResult | null;
  fcfs: Option | null;
  newOptionIds: string[];
  round: RoundStartedData | null;
  roundsEnded: number[];
  cards: Card[];
  vetoes: VetoData[];
  tentative: TentativeData | null;
  consensus: ConsensusData | null;
  fallback: FallbackData | null;
  narration: string | null;
  awaiting: AwaitingApprovalData | null;
  approved: ApprovedData | null;
  ended: RunEndedData | null;
  errors: string[];
}

const initial = (runId: string | null): RunState => ({
  runId, lastSeq: -1, connected: false, started: null, options: [], checks: {}, fallbackShadow: null, fcfs: null,
  newOptionIds: [], round: null, roundsEnded: [], cards: [], vetoes: [], tentative: null, consensus: null,
  fallback: null, narration: null, awaiting: null, approved: null, ended: null, errors: [],
});

type Act = { t: "reset"; runId: string | null } | { t: "conn"; on: boolean } | { t: "env"; env: Envelope };

function reduce(s: RunState, a: Act): RunState {
  if (a.t === "reset") return initial(a.runId);
  if (a.t === "conn") return { ...s, connected: a.on };
  const e = a.env;
  if (e.run_id !== s.runId || e.seq <= s.lastSeq) return s;
  const n: RunState = { ...s, lastSeq: e.seq };
  switch (e.type) {
    case "run_started":
      return { ...n, started: e.data };
    case "options": {
      const prev = new Set(s.options.map((o) => o.option_id));
      const newIds = s.options.length ? e.data.options.map((o) => o.option_id).filter((id) => !prev.has(id)) : [];
      return { ...n, options: e.data.options, checks: e.data.checks, fallbackShadow: e.data.fallback, fcfs: e.data.fcfs, newOptionIds: newIds };
    }
    case "round_started":
      return { ...n, round: e.data };
    case "agent_thinking":
      return { ...n, cards: [...s.cards, { kind: "thinking", round: e.data.round, agent: e.data.agent, seq: e.seq }] };
    case "agent_position": {
      const m = e.data;
      const cards = s.cards.filter((c) => !(c.kind === "thinking" && c.agent === m.agent && c.round === m.round));
      return { ...n, cards: [...cards, { kind: "position", round: m.round, agent: m.agent, seq: e.seq, msg: m }] };
    }
    case "counter_checked":
      return { ...n, cards: [...s.cards, { kind: "counter", round: e.data.round, agent: e.data.agent, seq: e.seq, cc: e.data }] };
    case "veto":
      return { ...n, vetoes: [...s.vetoes, e.data] };
    case "tentative":
      return { ...n, tentative: e.data };
    case "round_ended":
      return { ...n, roundsEnded: [...s.roundsEnded, e.data.round] };
    case "consensus":
      return { ...n, consensus: e.data };
    case "fallback":
      return { ...n, fallback: e.data };
    case "narration":
      return { ...n, narration: e.data.text };
    case "awaiting_approval":
      return { ...n, awaiting: e.data };
    case "approved":
      return { ...n, approved: e.data };
    case "run_ended":
      return { ...n, ended: e.data };
    case "error":
      return { ...n, errors: [...s.errors, `${e.data.fatal ? "FATAL: " : ""}${e.data.message}`] };
    default:
      return n;
  }
}

/** Subscribes to /api/runs/{runId}/stream and reduces SSE envelopes (CONTRACTS.md §3) into RunState. */
export function useRunStream(runId: string | null, url?: string): RunState {
  const [state, dispatch] = useReducer(reduce, runId, initial);

  useEffect(() => {
    dispatch({ t: "reset", runId });
    if (!runId) return;
    const es = new EventSource(url ?? api.streamUrl(runId));
    const onMsg = (ev: MessageEvent) => {
      try {
        dispatch({ t: "env", env: JSON.parse(ev.data) as Envelope });
      } catch {
        /* ignore malformed frames */
      }
    };
    EVENT_TYPES.forEach((t) => es.addEventListener(t, onMsg as EventListener));
    es.onopen = () => dispatch({ t: "conn", on: true });
    es.onerror = () => dispatch({ t: "conn", on: false });
    return () => es.close();
  }, [runId, url]);

  return state;
}

/** The plan the UI should treat as decided (consensus or fallback), if any. */
export const decidedPlan = (s: RunState): Option | null => s.consensus?.plan ?? s.fallback?.plan ?? null;
