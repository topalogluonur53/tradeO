import { useState, useEffect } from "react";
import { UserResponse, changePassword, createUser, getUsers } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { RefreshCw, KeyRound, UserPlus, Users } from "lucide-react";

export function ChangePasswordForm() {
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setMessage("");
    setError("");
    try {
      const res = await changePassword({ old_password: oldPassword, new_password: newPassword });
      setMessage(res.message || "Şifre başarıyla değiştirildi.");
      setOldPassword("");
      setNewPassword("");
    } catch (err: any) {
      setError(err.message || "Şifre değiştirilirken hata oluştu.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <div className="flex items-center gap-2 mb-4">
        <KeyRound className="h-5 w-5 text-accent" />
        <h2 className="text-sm font-black uppercase tracking-normal">Şifre Değiştir</h2>
      </div>
      
      {message && <div className="mb-4 text-sm text-teal-100">{message}</div>}
      {error && <div className="mb-4 text-sm text-rose-100">{error}</div>}

      <form onSubmit={handleSubmit} className="grid gap-3 max-w-sm">
        <label className="text-sm">
          <span className="block mb-1 text-textMuted">Mevcut Şifre</span>
          <input
            type="password"
            value={oldPassword}
            onChange={e => setOldPassword(e.target.value)}
            className="w-full rounded-md border border-line bg-background px-3 py-2 text-sm outline-none focus:border-accent"
            required
          />
        </label>
        <label className="text-sm">
          <span className="block mb-1 text-textMuted">Yeni Şifre</span>
          <input
            type="password"
            value={newPassword}
            onChange={e => setNewPassword(e.target.value)}
            className="w-full rounded-md border border-line bg-background px-3 py-2 text-sm outline-none focus:border-accent"
            required
          />
        </label>
        <Button variant="primary" type="submit" disabled={loading} className="mt-2">
          {loading ? "Kaydediliyor..." : "Şifreyi Değiştir"}
        </Button>
      </form>
    </section>
  );
}

export function UserManagement() {
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [error, setError] = useState("");

  const loadUsers = async () => {
    setLoading(true);
    try {
      const data = await getUsers();
      setUsers(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateLoading(true);
    setError("");
    try {
      await createUser({ username: newUsername, password: newPassword });
      setNewUsername("");
      setNewPassword("");
      await loadUsers();
    } catch (err: any) {
      setError(err.message || "Kullanıcı oluşturulamadı.");
    } finally {
      setCreateLoading(false);
    }
  };

  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <div className="flex items-center gap-2 mb-4">
        <Users className="h-5 w-5 text-accent" />
        <h2 className="text-sm font-black uppercase tracking-normal">Kullanıcı Yönetimi (Admin)</h2>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div>
          <h3 className="text-xs font-bold text-textMuted uppercase mb-3">Yeni Kullanıcı Ekle</h3>
          {error && <div className="mb-3 text-sm text-rose-100">{error}</div>}
          <form onSubmit={handleCreateUser} className="grid gap-3">
            <label className="text-sm">
              <span className="block mb-1 text-textMuted">Kullanıcı Adı</span>
              <input
                type="text"
                value={newUsername}
                onChange={e => setNewUsername(e.target.value)}
                className="w-full rounded-md border border-line bg-background px-3 py-2 text-sm outline-none focus:border-accent"
                required
              />
            </label>
            <label className="text-sm">
              <span className="block mb-1 text-textMuted">Şifre</span>
              <input
                type="password"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                className="w-full rounded-md border border-line bg-background px-3 py-2 text-sm outline-none focus:border-accent"
                required
              />
            </label>
            <Button variant="secondary" type="submit" disabled={createLoading} className="mt-2 w-fit">
              <UserPlus className="h-4 w-4 mr-2" />
              {createLoading ? "Oluşturuluyor..." : "Kullanıcı Oluştur"}
            </Button>
          </form>
        </div>

        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-bold text-textMuted uppercase">Mevcut Kullanıcılar</h3>
            <button onClick={loadUsers} className="text-textMuted hover:text-textPrimary" disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
          
          <div className="bg-background border border-line rounded-md overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead className="bg-panelMuted text-xs uppercase text-textMuted">
                <tr>
                  <th className="px-3 py-2 font-bold">ID</th>
                  <th className="px-3 py-2 font-bold">Kullanıcı Adı</th>
                  <th className="px-3 py-2 font-bold">Rol</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {users.map(u => (
                  <tr key={u.id}>
                    <td className="px-3 py-2">{u.id}</td>
                    <td className="px-3 py-2 font-semibold">{u.username}</td>
                    <td className="px-3 py-2 text-xs">
                      {u.is_admin ? (
                        <span className="text-teal-100 bg-teal-500/10 px-2 py-0.5 rounded">Admin</span>
                      ) : (
                        <span className="text-textMuted bg-panel px-2 py-0.5 rounded">User</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}
