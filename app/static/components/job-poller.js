// <job-poller> — компонент, который опрашивает GET /jobs/{jobId}
// и отрисовывает прогресс задачи.
//
// Атрибуты:
//   job-id       (обязательный)  uuid задачи
//   api-key      (опциональный)  если не указан — читается из localStorage["vkr_api_key"]
//   interval     (опциональный)  мс между опросами, default=1500
//   auto         (опциональный)  если "false" — не стартовать автоматически
//
// События:
//   job-poller:update  — каждый успешный опрос, detail = job
//   job-poller:done    — задача в терминальном статусе, detail = job

const TERMINAL = new Set(["completed", "failed", "cancelled"]);
const PROGRESS_BY_STATUS = {
    pending:     10,
    in_progress: 55,
    completed:   100,
    failed:      100,
    cancelled:   100,
};

class JobPoller extends HTMLElement {
    static get observedAttributes() { return ["job-id", "interval", "auto"]; }

    constructor() {
        super();
        this._timer = null;
        this._lastStatus = null;
    }

    connectedCallback() {
        this._render();
        if (this.getAttribute("auto") !== "false") {
            this.start();
        }
    }

    disconnectedCallback() { this.stop(); }

    attributeChangedCallback(name, oldV, newV) {
        if (oldV === newV) return;
        if (name === "job-id") {
            this.stop();
            this._render();
            if (this.isConnected && this.getAttribute("auto") !== "false") this.start();
        }
        if (name === "interval" && this._timer) {
            this.stop();
            this.start();
        }
    }

    get jobId() { return this.getAttribute("job-id"); }
    get apiKey() {
        return this.getAttribute("api-key")
            || (typeof localStorage !== "undefined" && localStorage.getItem("vkr_api_key"))
            || "";
    }
    get interval() {
        const v = parseInt(this.getAttribute("interval") || "1500", 10);
        return Number.isFinite(v) && v >= 200 ? v : 1500;
    }

    start() {
        if (!this.jobId) return;
        if (this._timer) clearInterval(this._timer);
        this._tick();
        this._timer = setInterval(() => this._tick(), this.interval);
    }

    stop() {
        if (this._timer) { clearInterval(this._timer); this._timer = null; }
    }

    async _tick() {
        if (!this.jobId) return;
        try {
            const r = await fetch(`/jobs/${this.jobId}`, {
                headers: this.apiKey ? { "X-API-Key": this.apiKey } : {},
            });
            if (!r.ok) {
                this._renderError(`HTTP ${r.status}`);
                this.stop();
                return;
            }
            const job = await r.json();
            this._applyJob(job);
            this.dispatchEvent(new CustomEvent("job-poller:update", { detail: job, bubbles: true }));
            if (TERMINAL.has(job.status)) {
                this.stop();
                this.dispatchEvent(new CustomEvent("job-poller:done", { detail: job, bubbles: true }));
            }
        } catch (err) {
            this._renderError(err.message);
            this.stop();
        }
    }

    _render() {
        this.innerHTML = `
            <div class="header" style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:6px;">
                <div style="font-family:ui-monospace,Consolas,monospace;font-size:12px;">
                    <span style="opacity:0.6">jobId:</span> <span data-job></span>
                </div>
                <span class="status-tag" data-status>—</span>
            </div>
            <div class="progress"><div class="bar" data-bar></div></div>
            <div data-resolution style="margin-bottom:8px;font-size:12px;"></div>
            <pre data-result style="margin:0;background:var(--code-bg,#f1f2f6);padding:10px;border-radius:6px;font-size:12px;white-space:pre-wrap;max-height:200px;overflow:auto;">ожидание…</pre>
        `;
        const $job = this.querySelector("[data-job]");
        if ($job) $job.textContent = this.jobId || "—";
    }

    _applyJob(job) {
        this.dataset.status = job.status;
        const $status = this.querySelector("[data-status]");
        if ($status) {
            $status.textContent = job.status;
            $status.className = "status-tag status-" + job.status;
        }
        const $bar = this.querySelector("[data-bar]");
        if ($bar) $bar.style.width = (PROGRESS_BY_STATUS[job.status] ?? 0) + "%";

        const $res = this.querySelector("[data-result]");
        if ($res) {
            const payload = job.status === "failed"
                ? (job.error || {})
                : (job.result ?? "ожидание…");
            $res.textContent = typeof payload === "string"
                ? payload
                : JSON.stringify(payload, null, 2);
        }

        const $reso = this.querySelector("[data-resolution]");
        if ($reso && job.llm_log) {
            const log = job.llm_log;
            $reso.innerHTML =
                `<span style="opacity:0.6">model:</span> `
                + `<span style="font-family:ui-monospace,Consolas,monospace">${log.actual_model}</span> `
                + `<span class="resolution-tag resolution-${log.model_resolution}" style="margin-left:6px">${log.model_resolution}</span>`
                + (log.duration_ms ? ` <span style="opacity:0.6;margin-left:6px">${log.duration_ms} ms</span>` : "");
        }
    }

    _renderError(msg) {
        this.dataset.status = "failed";
        const $status = this.querySelector("[data-status]");
        if ($status) {
            $status.textContent = "error";
            $status.className = "status-tag status-failed";
        }
        const $res = this.querySelector("[data-result]");
        if ($res) $res.textContent = "Ошибка опроса: " + msg;
    }
}

if (!customElements.get("job-poller")) {
    customElements.define("job-poller", JobPoller);
}
