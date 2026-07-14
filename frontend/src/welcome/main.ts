import "../index.css";
import "./welcome.css";

// The redirect-if-already-visited check lives in an inline <script> in
// index.html's <head>, not here — it has to run before paint, and a
// type="module" script (this one) is always deferred, which would let the
// Welcome screen flash for a returning visitor before redirecting.

// Must match the literal in index.html's <head> script — bump both
// together when the age gate or Privacy Policy changes in a way that
// requires re-consent from someone who already accepted an older version.
const CONSENT_VERSION = "1";

const consentCheckbox = document.getElementById("consent-checkbox") as HTMLInputElement | null;
const sayHello = document.getElementById("say-hello") as HTMLButtonElement | null;

consentCheckbox?.addEventListener("change", () => {
  if (sayHello) sayHello.disabled = !consentCheckbox.checked;
});

sayHello?.addEventListener("click", () => {
  if (!consentCheckbox?.checked) return; // belt-and-suspenders; button is disabled until checked
  localStorage.setItem("bandhu_visited", "1");
  localStorage.setItem("bandhu_consent_version", CONSENT_VERSION);
  location.href = "/app/";
});
