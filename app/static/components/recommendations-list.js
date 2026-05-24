// <recommendations-list> — список альтернативных правильных ответов студента,
// предложенных моделью преподавателю как кандидаты на принимаемые альтернативы.
//
// Атрибуты:
//   items     (опциональный) JSON-массив {text, rationale, confidence}
//   job-id    (опциональный) uuid; если задан — компонент сам загрузит
//             /jobs/{id}.result.recommendations
//   api-key   (опциональный) если не задан — берётся из localStorage
//
// Свойство:
//   .items = [...]  — программная установка списка
//
// Сортировка: по confidence от высокой к низкой.

class RecommendationsList extends HTMLElement {
    static get observedAttributes() { return ["items", "job-id"]; }

    constructor() {
        super();
        this._items = null;
    }

    set items(value) {
        this._items = Array.isArray(value) ? value : null;
        this._render();
    }
    get items() { return this._items; }

    connectedCallback() { this._init(); }

    attributeChangedCallback(name, oldV, newV) {
        if (oldV === newV) return;
        if (this.isConnected) this._init();
    }

    get apiKey() {
        return this.getAttribute("api-key")
            || (typeof localStorage !== "undefined" && localStorage.getItem("vkr_api_key"))
            || "";
    }

    async _init() {
        const raw = this.getAttribute("items");
        if (raw) {
            try { this._items = JSON.parse(raw); }
            catch { this._items = null; }
            this._render();
            return;
        }
        const jobId = this.getAttribute("job-id");
        if (jobId) {
            this._renderLoading();
            try {
                const r = await fetch(`/jobs/${jobId}`, {
                    headers: this.apiKey ? {"X-API-Key": this.apiKey} : {},
                });
                if (!r.ok) throw new Error("HTTP " + r.status);
                const job = await r.json();
                // Берём из result.recommendations (новая схема) либо result.items
                // (legacy, для обратной совместимости с другими ручками)
                this._items =
                    job?.result?.recommendations
                    ?? job?.result?.items
                    ?? [];
                this._render();
            } catch (err) {
                this._renderError(err.message);
            }
            return;
        }
        this._render();
    }

    _renderLoading() {
        this.innerHTML = `<div style="color:var(--text-muted,#777);font-size:13px;">загрузка вариантов…</div>`;
    }

    _renderError(msg) {
        this.innerHTML = `<div style="color:var(--danger,#c84a4a);font-size:13px;">не удалось загрузить: ${msg}</div>`;
    }

    _render() {
        if (!Array.isArray(this._items)) {
            this.innerHTML = `<div style="color:var(--text-muted,#777);font-size:13px;font-style:italic;">список не задан</div>`;
            return;
        }
        if (this._items.length === 0) {
            this.innerHTML = `<div style="color:var(--text-muted,#777);font-size:13px;font-style:italic;">вариантов нет</div>`;
            return;
        }
        const items = [...this._items].sort(
            (a, b) => (b.confidence ?? 0) - (a.confidence ?? 0)
        );
        const ol = document.createElement("ol");
        for (const it of items) {
            const li = document.createElement("li");

            const conf = document.createElement("span");
            conf.className = "confidence";
            const pct = Math.round(((it.confidence ?? 0) * 100));
            conf.textContent = pct + "%";

            const text = document.createElement("div");
            text.className = "item-text";
            text.textContent = it.text ?? "(пусто)";

            if (it.rationale) {
                const rat = document.createElement("div");
                rat.className = "item-rationale";
                rat.textContent = it.rationale;
                li.append(conf, text, rat);
            } else {
                li.append(conf, text);
            }
            ol.appendChild(li);
        }
        this.innerHTML = "";
        this.appendChild(ol);
    }
}

if (!customElements.get("recommendations-list")) {
    customElements.define("recommendations-list", RecommendationsList);
}
