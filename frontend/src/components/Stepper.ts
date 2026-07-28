export type JobStatus =
  | "PENDING"
  | "QUEUED"
  | "PROCESSING_COLMAP"
  | "PROCESSING_GSPLAT"
  | "PROCESSING_COLLISION"
  | "PROCESSING_EXPORT"
  | "COMPLETED"
  | "FAILED";

export interface StepperStep {
  id: string;
  label: string;
  icon: string;
}

export const PIPELINE_STEPS: StepperStep[] = [
  { id: "colmap", label: "COLMAP", icon: "📷" },
  { id: "gsplat", label: "GSPLAT Training", icon: "✨" },
  { id: "collision", label: "Collision Mesh", icon: "🧊" },
  { id: "ready", label: "Ready", icon: "🎯" },
];

const STATUS_TO_STEP: Record<string, number> = {
  PENDING: -1,
  QUEUED: 0,
  PROCESSING_COLMAP: 0,
  PROCESSING_GSPLAT: 1,
  PROCESSING_COLLISION: 2,
  PROCESSING_EXPORT: 3,
  COMPLETED: 4,
  FAILED: -2,
};

export type StepState = "pending" | "active" | "complete" | "failed";

export interface StepperState {
  steps: Array<StepperStep & { state: StepState; detail?: string }>;
  activeIndex: number;
  failed: boolean;
  errorMessage?: string;
}

function extractStageDetail(status: JobStatus, logs: string | null): string | undefined {
  if (!logs) return undefined;
  const lines = logs.split("\n").reverse();
  const prefixMap: Record<string, string> = {
    PROCESSING_COLMAP: "[COLMAP",
    PROCESSING_GSPLAT: "[gsplat",
    PROCESSING_COLLISION: "[collision",
    PROCESSING_EXPORT: "[export",
  };
  const prefix = prefixMap[status];
  if (!prefix) return undefined;
  for (const line of lines) {
    if (line.includes(prefix)) {
      const match = line.match(/\] (.+)$/);
      return match ? match[1] : line.trim();
    }
  }
  return undefined;
}

function extractErrorMessage(logs: string | null): string | undefined {
  if (!logs) return undefined;
  const lines = logs.split("\n").reverse();
  for (const line of lines) {
    if (line.includes("ERROR:")) {
      return line.replace(/^.*ERROR:\s*/, "").trim();
    }
    if (line.includes("[") && line.match(/\[(RuntimeError|Error|.*Error)\]/)) {
      return line.trim();
    }
  }
  return undefined;
}

export function buildStepperState(status: JobStatus, logs: string | null): StepperState {
  const activeIndex = STATUS_TO_STEP[status] ?? -1;
  const failed = status === "FAILED";
  const detail = extractStageDetail(status, logs);
  const errorMessage = failed ? extractErrorMessage(logs) : undefined;

  const steps = PIPELINE_STEPS.map((step, index) => {
    let state: StepState = "pending";
    if (failed) {
      if (index === Math.max(0, activeIndex)) {
        state = "failed";
      } else if (index < Math.max(0, activeIndex)) {
        state = "complete";
      }
    } else if (status === "COMPLETED") {
      state = "complete";
    } else if (index < activeIndex) {
      state = "complete";
    } else if (index === activeIndex) {
      state = "active";
    }

    return {
      ...step,
      state,
      detail: index === activeIndex ? detail : undefined,
    };
  });

  return { steps, activeIndex, failed, errorMessage };
}

export class PipelineStepper {
  private container: HTMLElement;

  constructor(containerId: string) {
    const el = document.getElementById(containerId);
    if (!el) throw new Error(`Stepper container #${containerId} not found`);
    this.container = el;
  }

  update(status: JobStatus, logs: string | null): void {
    const state = buildStepperState(status, logs);
    this.container.innerHTML = this.render(state);
    this.container.style.display =
      status === "PENDING" ? "none" : "block";
  }

  private render(state: StepperState): string {
    const errorBlock = state.failed && state.errorMessage
      ? `<div class="stepper-error">${escapeHtml(state.errorMessage)}</div>`
      : "";

    const stepsHtml = state.steps
      .map((step, i) => {
        const connector =
          i < state.steps.length - 1
            ? `<div class="stepper-connector ${step.state === "complete" ? "complete" : ""}"></div>`
            : "";

        return `
          <div class="stepper-step ${step.state}" data-step="${step.id}">
            <div class="stepper-node">
              <span class="stepper-icon">${step.state === "complete" ? "✓" : step.icon}</span>
            </div>
            <div class="stepper-label">${step.label}</div>
            ${step.detail ? `<div class="stepper-detail">${escapeHtml(step.detail)}</div>` : ""}
          </div>
          ${connector}
        `;
      })
      .join("");

    return `
      <div class="stepper-glass">
        <div class="stepper-track">${stepsHtml}</div>
        ${errorBlock}
      </div>
    `;
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
