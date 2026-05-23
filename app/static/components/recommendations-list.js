// <recommendations-list> — компонент-список рекомендаций.
// Может работать в двух режимах:
//   1. Декларативный: items=<json-строка> в атрибуте — отрисовать как есть
//   2. Загрузка: job-id=<uuid> + api-key — забрать /jobs/{jobId} и взять result.items
//
// Атрибуты:
//   items        (опциональный) JSON-массив объектов {title, detail, priority}
//   job-id       (опциональный) uuid; если задан — компонент сам загрузит результат
//   api-key      (опциональный) для load-режима
//
// Свойство:
//   .items = [...]  — программная установка списка

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
                this._items = job?.result?.items ?? [];
                this._render();
            } catch (err) {
                this._renderError(err.message);
            }
            return;
        }
        this._render();
    }

    _renderLoading() {
        this.innerHTML = `<div style="color:var(--text-muted,#777);font-size:13px;">загрузка рекомендаций…</div>`;
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
            this.innerHTML = `<div style="color:var(--text-muted,#777);font-size:13px;font-style:italic;">рекомендаций нет</div>`;
            return;
        }
        const items = [...this._items].sort((a, b) => (a.priority ?? 99) - (b.priority ?? 99));
        const ol = document.createElement("ol");
        for (const it of items) {
            const li = document.createElement("li");
            const prio = document.createElement("span");
            prio.className = "priority";
            prio.textContent = "P" + (it.priority ?? "?");
            const title = document.createElement("span");
            title.className = "item-title";
            title.textContent = it.title ?? "(без названия)";
            const detail = document.createElement("div");
            detail.className = "item-detail";
            detail.textContent = it.detail ?? "";
            li.append(prio, title, detail);
            ol.appendChild(li);
        }
        this.innerHTML = "";
        this.appendChild(ol);
    }
}

if (!customElements.get("recommendations-list")) {
    customElements.define("recommendations-list", RecommendationsList);
}
