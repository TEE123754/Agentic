"use strict";

const element = (id) => document.getElementById(id);
const query = new URLSearchParams(location.search);
const knownVariants = Array.from(element("variant").options, (option) => option.value);
const variant = knownVariants.includes(query.get("variant")) ? query.get("variant") : "healthy";
const suppliedRunId = query.get("run_id");
const runId = suppliedRunId && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(suppliedRunId)
  ? suppliedRunId : crypto.randomUUID();
let state;
let generatedEmail;
let generation = 0;
element("variant").value = variant;

async function request(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : {"Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok && !Object.hasOwn(data, "ok")) {
    throw new Error(typeof data.detail === "string" ? data.detail : "Fixture request failed");
  }
  return data;
}

async function bootstrap() {
  state = await request("/fixture/runs", {run_id: runId, variant});
  const account = await request(`/fixture/runs/${runId}/accounts`, {});
  generatedEmail = account.email;
  element("email").value = state.defects.generic_validation ? "test.user" : generatedEmail;
  element("price-details").textContent = state.defects.hidden_shipping
    ? "Product price shown above."
    : "Shipping $5. Total including shipping: $70.";
  element("setup-status").textContent = `Ready · ${variant} · Synthetic account created`;
  element("start").disabled = false;
}

element("switch-variant").addEventListener("click", () => {
  location.assign(`/?variant=${encodeURIComponent(element("variant").value)}`);
});

element("start").addEventListener("click", () => {
  if (!state || state.defects.dead_button) return;
  element("product").hidden = true;
  element("checkout").hidden = false;
  element("email").focus();
});

element("checkout-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const thisGeneration = generation;
  element("validation").textContent = "";
  element("email").removeAttribute("aria-invalid");
  if (!state.defects.delayed_feedback) {
    element("continue").disabled = true;
    element("setup-status").textContent = "Checking synthetic details…";
  } else {
    // Deliberate defect: no feedback or button lock during the waiting interval.
    await new Promise((resolve) => setTimeout(resolve, 2500));
  }
  if (thisGeneration !== generation) return;
  try {
    const result = await request(`/fixture/runs/${runId}/checkout`, {email: element("email").value});
    if (thisGeneration !== generation) return;
    if (!result.ok) {
      element("validation").textContent = result.message;
      if (result.field === "email") {
        element("email").setAttribute("aria-invalid", "true");
        element("email").focus();
      }
      element("setup-status").textContent = "Correct the form to continue.";
      return;
    }
    element("checkout").hidden = true;
    element("review").hidden = false;
    element("setup-status").textContent = "Order review reached. No payment or external dispatch occurred.";
  } catch (error) {
    element("validation").textContent = error.message;
  } finally {
    if (thisGeneration === generation) element("continue").disabled = false;
  }
});

element("delivery").addEventListener("click", () => {
  if (!state) return;
  element("close-delivery").disabled = state.defects.focus_trap;
  element("delivery-dialog").showModal();
  if (state.defects.focus_trap) {
    element("delivery-dialog").tabIndex = 0;
    element("delivery-dialog").focus();
  }
});
element("close-delivery").addEventListener("click", () => element("delivery-dialog").close());
element("delivery-dialog").addEventListener("cancel", (event) => {
  if (state.defects.focus_trap) event.preventDefault();
});
element("delivery-dialog").addEventListener("keydown", (event) => {
  if (state.defects.focus_trap && ["Tab", "Escape"].includes(event.key)) event.preventDefault();
});

element("reset").addEventListener("click", async () => {
  generation += 1;
  element("start").disabled = true;
  try {
    await request(`/fixture/runs/${runId}/reset`, {});
    element("delivery-dialog").close();
    element("product").hidden = false;
    element("checkout").hidden = true;
    element("review").hidden = true;
    element("validation").textContent = "";
    element("continue").disabled = false;
    await bootstrap();
  } catch (error) {
    element("setup-status").textContent = error.message;
  }
});

bootstrap().catch((error) => { element("setup-status").textContent = error.message; });
