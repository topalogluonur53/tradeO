"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, UserPlus } from "lucide-react";
import { register, login, setToken } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      // 1. Register the user
      await register(email, password);
      
      // 2. Automatically log them in
      const formData = new FormData();
      formData.append("username", email);
      formData.append("password", password);
      
      const response = await login(formData);
      setToken(response.access_token);
      
      // 3. Redirect to dashboard
      router.push("/");
    } catch (err: any) {
      setError(err instanceof Error ? err.message : "Kayıt olurken bir hata oluştu.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4 text-textPrimary">
      <div className="w-full max-w-md rounded-lg border border-line bg-panel p-8 shadow-xl">
        <div className="mb-8 flex flex-col items-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-xl bg-accent/10">
            <Bot className="h-8 w-8 text-accent" />
          </div>
          <h1 className="text-2xl font-black uppercase tracking-widest text-textPrimary">NEXUS AI</h1>
          <p className="mt-2 text-sm text-textMuted">Kripto Kağıt İşlem Terminali</p>
        </div>

        <form onSubmit={handleRegister} className="space-y-4">
          {error && (
            <div className="rounded-md border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-rose-200">
              {error}
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-xs font-bold uppercase tracking-wide text-textMuted">
              E-posta Adresi
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-line bg-background px-4 py-2.5 text-sm outline-none transition-colors focus:border-accent"
              placeholder="ornek@nexus.ai"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-bold uppercase tracking-wide text-textMuted">
              Parola
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-line bg-background px-4 py-2.5 text-sm outline-none transition-colors focus:border-accent"
              placeholder="En az 6 karakter"
              minLength={6}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="mt-6 flex w-full items-center justify-center gap-2 rounded-md bg-accent px-4 py-3 text-sm font-bold uppercase tracking-wide text-slate-950 transition hover:bg-accent/90 disabled:opacity-50"
          >
            {loading ? "Hesap Oluşturuluyor..." : (
              <>
                <UserPlus className="h-4 w-4" /> Kayıt Ol
              </>
            )}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-textMuted">
          Zaten hesabınız var mı?{" "}
          <button
            type="button"
            onClick={() => router.push("/login")}
            className="font-bold text-accent hover:underline"
          >
            Giriş Yapın
          </button>
        </p>
      </div>
    </div>
  );
}
