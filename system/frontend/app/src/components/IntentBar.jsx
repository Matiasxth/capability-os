import React from "react";

export default function IntentBar({ intent, onIntentChange, onSubmit, loading }) {
  return (
    <section className="intent-bar">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <label htmlFor="intent-input">What do you want Capability OS to do?</label>
        <div className="intent-row">
          <input
            id="intent-input"
            type="text"
            value={intent}
            placeholder="Ej: abrir whatsapp web, buscar MatiasXth y enviar 'hola'"
            onChange={(event) => onIntentChange(event.target.value)}
          />
          <button type="submit" disabled={loading || !intent.trim()}>
            {loading ? "Planning..." : "Generate Plan"}
          </button>
        </div>
      </form>
    </section>
  );
}
