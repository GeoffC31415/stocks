export type AuthSession = {
  mode: 'local' | 'basic' | 'passkey';
  authenticated: boolean;
  passkey_authenticated: boolean;
  can_register: boolean;
  expires_at: number | null;
};
export type PasskeyCredential = { id: string; label: string; created_at: number; last_used_at: number | null };
