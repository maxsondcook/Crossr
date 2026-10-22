const KEY = "crossr-sales-desk-v1";

function seedClients() {
  return [1, 2, 3, 4].map((n) => ({
    id: `c${n}`,
    name: `Client ${n}`,
    sex: "",
    color: "",
    maxPrice: "",
    height: "",
  }));
}

function empty() {
  return { clients: seedClients(), dismissed: {}, notes: {}, stars: {} };
}

export function loadDesk() {
  if (typeof window === "undefined") return empty();
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || "{}");
    const clients = Array.isArray(saved.clients) && saved.clients.length ? saved.clients : seedClients();
    return { ...empty(), ...saved, clients };
  } catch {
    return empty();
  }
}

export function saveDesk(next) {
  localStorage.setItem(KEY, JSON.stringify(next));
  return next;
}

export function deskKey(mode, catalogId) {
  return `${mode}:${catalogId}`;
}
