import { FormEvent, useState } from "react";
import { Loader2, LockKeyhole, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { Button, Input, Label, Toast } from "@/components/ui";

export function LoginPage({ setupRequired, onLoggedIn }: { setupRequired: boolean; onLoggedIn: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      if (setupRequired) await api.setup(username, password, confirmPassword);
      else await api.login(username, password);
      // 会话 Cookie 可能被浏览器直接丢弃（典型情况：纯 HTTP 页面收到带 Secure 标记的 Cookie）。
      // 先确认一次再进控制台，否则用户只会看到刚登录就被 401 弹回来，看不到原因。
      const me = await api.authMe().catch(() => null);
      if (me && !me.authenticated) {
        setError(
          "账号已就绪，但浏览器没有保存会话 Cookie，无法进入控制台。" +
            "请改用 http://127.0.0.1:8787 访问，或用 HTTPS 部署；" +
            "也可以设置 GROK_WEB_COOKIE_SECURE=0 后重启服务。"
        );
        return;
      }
      onLoggedIn();
    } catch (err: any) {
      setError(err.message || "登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-[100dvh] items-center justify-center bg-background px-4 py-8">
      <form onSubmit={submit} className="w-full max-w-md rounded-3xl border bg-card p-6 shadow-card sm:p-8">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Sparkles className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">Grok Register</h1>
            <p className="text-sm text-muted-foreground">{setupRequired ? "首次创建管理员账号" : "公网控制台登录"}</p>
          </div>
        </div>
        <div className="mb-6 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{setupRequired ? "首次访问请创建唯一管理员账号，创建后不能再新增账号。" : "请输入管理员账号和密码。"}</span>
        </div>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="login-username">账号</Label>
            <Input id="login-username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </div>
          {setupRequired ? (
            <div className="space-y-2">
              <Label htmlFor="login-confirm-password">确认密码</Label>
              <Input id="login-confirm-password" type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
            </div>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="login-password">密码</Label>
            <Input id="login-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <Button className="w-full" type="submit" disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <LockKeyhole className="h-4 w-4" aria-hidden="true" />}
            {setupRequired ? "创建并登录" : "登录"}
          </Button>
        </div>
        <Toast message="" />
      </form>
    </main>
  );
}
