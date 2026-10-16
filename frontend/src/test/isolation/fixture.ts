// Deliberately mutable: each test file must get a fresh module instance.
export const state = { visits: 0 };
export const identity = () => "real";
