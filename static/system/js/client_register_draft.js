(function () {
    "use strict";

    var form = document.querySelector("[data-client-draft-form]");
    if (!form || !window.localStorage) {
        return;
    }

    var draftKey = form.dataset.draftKey || "visary-client-register-draft-v1";
    var ttlMs = Number(form.dataset.draftTtlMs || 7 * 24 * 60 * 60 * 1000);
    var draftNote = document.querySelector("[data-client-draft-note]");
    var draftLabel = document.querySelector("[data-client-draft-label]");
    var draftClearButton = document.querySelector("[data-client-draft-clear]");
    var saveTimer = null;

    function isSensitiveField(field) {
        if (!field || !field.name) {
            return true;
        }
        return field.name === "csrfmiddlewaretoken"
            || field.name === "acao"
            || field.name === "action"
            || field.name === "form_type"
            || field.type === "password"
            || field.type === "file"
            || /password|senha/i.test(field.name);
    }

    function readDraft() {
        try {
            var raw = window.localStorage.getItem(draftKey);
            if (!raw) {
                return null;
            }
            var parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== "object" || !parsed.savedAt || !parsed.fields) {
                window.localStorage.removeItem(draftKey);
                return null;
            }
            if (Date.now() - parsed.savedAt > ttlMs) {
                window.localStorage.removeItem(draftKey);
                return null;
            }
            return parsed;
        } catch (_error) {
            return null;
        }
    }

    function setDraftMessage(message, restored) {
        if (draftLabel) {
            draftLabel.textContent = message;
        }
        if (draftNote) {
            draftNote.classList.remove("is-hidden");
            draftNote.classList.toggle("is-restored", Boolean(restored));
        }
    }

    function hideDraftNote() {
        if (draftNote) {
            draftNote.classList.add("is-hidden");
            draftNote.classList.remove("is-restored");
        }
    }

    function clearDraft() {
        try {
            window.localStorage.removeItem(draftKey);
        } catch (_error) {
            return;
        }
        hideDraftNote();
    }

    function collectFields() {
        var values = {};
        form.querySelectorAll("input[name], select[name], textarea[name]").forEach(function (field) {
            if (isSensitiveField(field)) {
                return;
            }
            if (field.type === "radio") {
                if (field.checked) {
                    values[field.name] = field.value;
                }
                return;
            }
            if (field.type === "checkbox") {
                values[field.name] = Boolean(field.checked);
                return;
            }
            if (field.tagName === "SELECT" && field.multiple) {
                values[field.name] = Array.from(field.selectedOptions).map(function (option) {
                    return option.value;
                });
                return;
            }
            values[field.name] = field.value || "";
        });
        return values;
    }

    function hasValue(value) {
        if (Array.isArray(value)) {
            return value.length > 0;
        }
        if (typeof value === "boolean") {
            return value;
        }
        return String(value || "").trim() !== "";
    }

    function saveDraft() {
        var fields = collectFields();
        var hasData = Object.keys(fields).some(function (name) {
            return hasValue(fields[name]);
        });

        if (!hasData) {
            clearDraft();
            return;
        }

        try {
            window.localStorage.setItem(draftKey, JSON.stringify({
                savedAt: Date.now(),
                stageId: form.dataset.currentStageId || "",
                fields: fields
            }));
            setDraftMessage("Rascunho salvo", false);
        } catch (_error) {
            return;
        }
    }

    function queueSave() {
        window.clearTimeout(saveTimer);
        saveTimer = window.setTimeout(saveDraft, 250);
    }

    function restoreValue(fieldName, value) {
        var safeName = fieldName.replace(/"/g, '\\"');
        var fields = Array.from(form.querySelectorAll('[name="' + safeName + '"]'));
        if (!fields.length) {
            return;
        }

        var sample = fields[0];
        if (sample.type === "radio") {
            fields.forEach(function (field) {
                if (!field.checked && String(field.value) === String(value)) {
                    field.checked = true;
                    field.dispatchEvent(new Event("change", { bubbles: true }));
                }
            });
            return;
        }

        if (sample.type === "checkbox") {
            if (!sample.checked && Boolean(value)) {
                sample.checked = true;
                sample.dispatchEvent(new Event("change", { bubbles: true }));
            }
            return;
        }

        if (sample.tagName === "SELECT" && sample.multiple) {
            var values = Array.isArray(value) ? value.map(String) : [];
            Array.from(sample.options).forEach(function (option) {
                if (!option.selected && values.indexOf(String(option.value)) !== -1) {
                    option.selected = true;
                }
            });
            sample.dispatchEvent(new Event("change", { bubbles: true }));
            return;
        }

        if (String(sample.value || "").trim() !== "") {
            return;
        }

        sample.value = value || "";
        sample.dispatchEvent(new Event("input", { bubbles: true }));
        sample.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function restoreDraft() {
        if (form.dataset.canRestoreDraft !== "true") {
            return false;
        }
        var draft = readDraft();
        if (!draft) {
            return false;
        }
        Object.keys(draft.fields || {}).forEach(function (fieldName) {
            restoreValue(fieldName, draft.fields[fieldName]);
        });
        setDraftMessage("Rascunho recuperado", true);
        return true;
    }

    form.addEventListener("input", queueSave);
    form.addEventListener("change", queueSave);

    if (draftClearButton) {
        draftClearButton.addEventListener("click", clearDraft);
    }

    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "hidden") {
            saveDraft();
        }
    });
    window.addEventListener("beforeunload", saveDraft);

    var restoredDraft = restoreDraft();
    if (!restoredDraft && readDraft()) {
        setDraftMessage("Rascunho salvo", false);
    }
}());
