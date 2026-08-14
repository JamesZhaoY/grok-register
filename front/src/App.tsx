import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { DashboardPage } from "@/pages/Dashboard";
import { AccountsPage } from "@/pages/Accounts";
import { RegisterPage } from "@/pages/Register";
import { SettingsPage } from "@/pages/Settings";
import { api } from "@/lib/api";
import { LoginPage } from "@/pages/Login";

export default function App() {
  const [jobRunning, setJobRunning] = useState(false);
  const [jobPolling, setJobPolling] = useState(true);
  const [authLoading, setAuthLoading] = useState(true);
  const [auth, setAuth] = useState({ enabled: false, setup_required: true, authenticated: false });

  useEffect(() => {
    const onAuthRequired = (event: Event) => {
      const setupRequired = !!(event as CustomEvent<{ setupRequired?: boolean }>).detail?.setupRequired;
      setAuth({ enabled: !setupRequired, setup_required: setupRequired, authenticated: false });
    };
    const onJobState = (event: Event) => {
      const running = !!(event as CustomEvent<{ running?: boolean }>).detail?.running;
      setJobRunning(running);
      setJobPolling(running);
    };
    window.addEventListener("grok-auth-required", onAuthRequired);
    window.addEventListener("grok-job-state", onJobState);
    api.authMe().then((data) => setAuth(data)).catch(() => setAuth({ enabled: true, setup_required: false, authenticated: false })).finally(() => setAuthLoading(false));
    return () => {
      window.removeEventListener("grok-auth-required", onAuthRequired);
      window.removeEventListener("grok-job-state", onJobState);
    };
  }, []);

  useEffect(() => {
    if (authLoading || (auth.enabled && !auth.authenticated) || !jobPolling) return;
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const data = await api.job();
        if (!alive) return;
        const running = !!data.job?.running;
        setJobRunning(running);
        if (running) timer = window.setTimeout(tick, 3000);
        else setJobPolling(false);
      } catch {
        if (alive) timer = window.setTimeout(tick, 5000);
      }
    };
    void tick();
    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [authLoading, auth.enabled, auth.authenticated, jobPolling]);

  if (authLoading) {
    return <div className="flex min-h-[100dvh] items-center justify-center text-muted-foreground">加载中…</div>;
  }
  if (auth.setup_required || (auth.enabled && !auth.authenticated)) {
    return <LoginPage setupRequired={!!auth.setup_required} onLoggedIn={() => setAuth({ enabled: true, setup_required: false, authenticated: true })} />;
  }

  const logout = async () => {
    try {
      await api.logout();
    } finally {
      setAuth({ enabled: true, setup_required: false, authenticated: false });
      setJobRunning(false);
      setJobPolling(false);
    }
  };

  return (
    <Routes>
      <Route element={<Layout jobRunning={jobRunning} onLogout={auth.enabled ? logout : undefined} />}>
        <Route index element={<DashboardPage />} />
        <Route path="accounts" element={<AccountsPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
