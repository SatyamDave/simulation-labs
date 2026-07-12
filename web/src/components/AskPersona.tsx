import { useEffect, useRef, useState } from "react";
import {
  artifactUrl,
  askPersona,
  askPersonaAudio,
  type AskResponse,
} from "../api";
import { blobToWav } from "../wav";

// Live Q&A with a dead persona: type a question (POST /runs/{id}/ask) or
// speak one into the mic (recorded → PCM16 WAV → POST /runs/{id}/ask-audio).
// Either way the answer is grounded in the persona's real action trace and
// voiced in its cloned voice. Live (server-backed) reports only — the parent
// hides this in the offline demo.

type Phase = "idle" | "recording" | "thinking" | "answered";

interface Props {
  runId: string;
  personaId: string;
  name: string;
}

export function AskPersona({ runId, personaId, name }: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  // Never leave the mic open after unmount.
  useEffect(() => {
    return () => stopTracks(recorderRef.current);
  }, []);

  const busy = phase === "recording" || phase === "thinking";

  async function submitText() {
    const q = question.trim();
    if (!q || busy) return;
    setPhase("thinking");
    setError(null);
    try {
      const res = await askPersona(runId, personaId, q);
      setAnswer({ ...res, question: q });
      setPhase("answered");
    } catch (e) {
      setError(e instanceof Error ? e.message : "network error");
      setPhase("idle");
    }
  }

  async function startRecording() {
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("microphone unavailable or permission denied");
      return;
    }
    const recorder = new MediaRecorder(stream);
    chunksRef.current = [];
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = async () => {
      stopTracks(recorder);
      setPhase("thinking");
      try {
        const recorded = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        const wav = await blobToWav(recorded);
        const res = await askPersonaAudio(runId, personaId, wav);
        setAnswer(res);
        setPhase("answered");
      } catch (e) {
        setError(e instanceof Error ? e.message : "network error");
        setPhase("idle");
      }
    };
    recorderRef.current = recorder;
    recorder.start();
    setPhase("recording");
  }

  function stopRecording() {
    recorderRef.current?.stop();
  }

  return (
    <div className="border-t border-border pt-3">
      <p className="text-xs text-muted-foreground mb-2">
        Ask {name} a question — typed or spoken
      </p>

      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void submitText();
        }}
      >
        <input
          className="min-w-0 flex-1 px-3 py-1.5 text-sm bg-background border border-border rounded-lg outline-none focus:border-ring focus:ring-2 focus:ring-ring/25 transition-colors placeholder:text-muted-foreground/50"
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Why did you give up?"
          aria-label={`Question for ${name}`}
          disabled={busy}
        />
        <button
          type="submit"
          className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-40"
          disabled={!question.trim() || busy}
        >
          Ask
        </button>
        <button
          type="button"
          className={`p-2 rounded-lg border transition-colors ${
            phase === "recording"
              ? "border-fail text-fail"
              : "border-border text-muted-foreground hover:text-foreground hover:bg-hover"
          }`}
          onClick={phase === "recording" ? stopRecording : startRecording}
          disabled={phase === "thinking"}
          aria-label={
            phase === "recording" ? "Stop recording" : "Record a spoken question"
          }
          title={
            phase === "recording" ? "Stop recording" : "Record a spoken question"
          }
        >
          {phase === "recording" ? <StopIcon /> : <MicIcon />}
        </button>
      </form>

      {phase === "recording" && (
        <p className="flex items-center gap-1.5 font-mono text-[11px] text-fail mt-2">
          <span
            className="w-1.5 h-1.5 rounded-full bg-fail animate-pulse shrink-0"
            aria-hidden="true"
          />
          recording — click to stop
        </p>
      )}
      {phase === "thinking" && (
        <p className="font-mono text-[11px] text-muted-foreground mt-2">
          thinking…
        </p>
      )}
      {error && (
        <p className="font-mono text-[11px] text-fail mt-2">{error}</p>
      )}

      {answer && phase === "answered" && (
        <div className="flex flex-col gap-2 mt-3">
          {answer.question && (
            <p className="font-mono text-[11px] text-muted-foreground">
              you asked — “{answer.question}”
            </p>
          )}
          {answer.audio_url && (
            <audio
              className="w-full"
              controls
              autoPlay
              src={artifactUrl(answer.audio_url)}
            />
          )}
          <blockquote className="border-l-2 border-border pl-3 text-sm leading-relaxed">
            “{answer.text}”
          </blockquote>
        </div>
      )}
    </div>
  );
}

function MicIcon() {
  return (
    <svg
      className="w-4 h-4"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
      <path d="M19 11a7 7 0 0 1-14 0" />
      <line x1="12" y1="18" x2="12" y2="22" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg
      className="w-4 h-4"
      fill="currentColor"
      stroke="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <rect x="6" y="6" width="12" height="12" rx="1.5" />
    </svg>
  );
}

function stopTracks(recorder: MediaRecorder | null) {
  recorder?.stream.getTracks().forEach((t) => t.stop());
}
