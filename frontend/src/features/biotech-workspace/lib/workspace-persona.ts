/** Retain existing storage identities; use a stable default only for unassigned queries. */
export function workspacePersonaId(personas: Array<{ persona_id: number; name: string; role: string }>, saved?: number | ''): number | '' {
  if (saved !== undefined && saved !== '' && personas.some(p=>p.persona_id===saved)) return saved;
  const stable = [...personas].sort((a,b)=>a.persona_id-b.persona_id);
  return (stable.find(p=>/literature|evidence|benchmark/i.test(`${p.name} ${p.role}`)) || stable[0])?.persona_id ?? '';
}
