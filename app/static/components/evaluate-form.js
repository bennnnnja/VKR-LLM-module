// <evaluate-form> — форма оценки развёрнутого ответа.
// Отправляет POST /evaluate/task, получает jobId и встраивает <job-poller>.
//
// Атрибуты:
//   api-key  (опциональный)  если не указан — читается из localStorage
//   max-score (опциональный) default=5
//
// События:
//   evaluate-form:submitted  detail = {jobId}
//   evaluate-form:done       detail = job  (терминальный статус)

class EvaluateForm extends HTMLElement {
    static get observedAttributes() { return ["api-key", "max-score"]; }

    connectedCallback() { this._render(); this._wire(); }

    get apiKey() {
        return this.getAttribute("api-key")
            || (typeof localStorage !== "undefined" && localStorage.getItem("vkr_api_key"))
            || "";
    }
    get maxScore() {
        return parseFloat(this.getAttribute("max-score") || "5");
    }

    _render() {
        this.innerHTML = `
            <form data-form style="display:flex;flex-direction:column;gap:10px;">
                <div>
                    <label style="display:block;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-muted,#777);margin-bottom:4px;">Текст задания</label>
                    <textarea data-task style="width:100%;min-height:60px;padding:8px;border:1px solid var(--border,#ddd);border-radius:6px;font-family:inherit;font-size:13px;background:var(--code-bg,#f7f7f7);color:inherit;">Опишите различия между процессом и потоком в ОС.</textarea>
                </div>
                <div>
                    <label style="display:block;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-muted,#777);margin-bottom:4px;">Эталонный ответ</label>
                    <textarea data-ref style="width:100%;min-height:60px;padding:8px;border:1px solid var(--border,#ddd);border-radius:6px;font-family:inherit;font-size:13px;background:var(--code-bg,#f7f7f7);color:inherit;">Процесс — независимая единица выполнения с собственным адресным пространством. Поток — поток выполнения внутри процесса, разделяет память с другими потоками того же процесса.</textarea>
                </div>
                <div>
                    <label style="display:block;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-muted,#777);margin-bottom:4px;">Ответ студента</label>
                    <textarea data-student style="width:100%;min-height:60px;padding:8px;border:1px solid var(--border,#ddd);border-radius:6px;font-family:inherit;font-size:13px;background:var(--code-bg,#f7f7f7);color:inherit;">Процесс — это запущенная программа, поток — часть процесса, у потоков общая память.</textarea>
                </div>
                <div style="display:flex;justify-content:flex-end;">
                    <button type="submit" class="primary" style="padding:8px 16px;border-radius:6px;border:none;background:var(--primary,#4a5fc1);color:white;font-weight:500;cursor:pointer;">Оценить</button>
                </div>
            </form>
            <div data-mount style="margin-top:12px;"></div>
        `;
    }

    _wire() {
        const $form = this.querySelector("[data-form]");
        $form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const body = {
                task_text:        this.querySelector("[data-task]").value,
                reference_answer: this.querySelector("[data-ref]").value,
                student_answer:   this.querySelector("[data-student]").value,
                max_score:        this.maxScore,
            };
            try {
                const r = await fetch("/evaluate/task", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        ...(this.apiKey ? {"X-API-Key": this.apiKey} : {}),
                    },
                    body: JSON.stringify(body),
                });
                const data = await r.json().catch(() => ({}));
                if (!r.ok) {
                    this._renderError("HTTP " + r.status + ": " + JSON.stringify(data));
                    return;
                }
                this.dispatchEvent(new CustomEvent("evaluate-form:submitted", {
                    detail: {jobId: data.jobId}, bubbles: true,
                }));
                this._mountPoller(data.jobId);
            } catch (err) {
                this._renderError("Ошибка сети: " + err.message);
            }
        });
    }

    _mountPoller(jobId) {
        const mount = this.querySelector("[data-mount]");
        mount.innerHTML = "";
        const poller = document.createElement("job-poller");
        poller.setAttribute("job-id", jobId);
        if (this.apiKey) poller.setAttribute("api-key", this.apiKey);
        poller.addEventListener("job-poller:done", (e) => {
            this.dispatchEvent(new CustomEvent("evaluate-form:done", {
                detail: e.detail, bubbles: true,
            }));
        });
        mount.appendChild(poller);
    }

    _renderError(msg) {
        const mount = this.querySelector("[data-mount]");
        mount.innerHTML = `<div style="padding:10px;color:var(--danger,#c84a4a);font-size:13px;">${msg}</div>`;
    }
}

if (!customElements.get("evaluate-form")) {
    customElements.define("evaluate-form", EvaluateForm);
}
