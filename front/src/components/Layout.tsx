import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  CircleDot,
  Database,
  LayoutDashboard,
  LogOut,
  PlayCircle,
  Settings,
  Sparkles,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { to: "/", label: "仪表盘", shortLabel: "首页", icon: LayoutDashboard },
  { to: "/accounts", label: "账号管理", shortLabel: "账号", icon: Users },
  { to: "/register", label: "启动注册", shortLabel: "注册", icon: PlayCircle },
  { to: "/settings", label: "系统设置", shortLabel: "设置", icon: Settings },
];

function StatusPill({ running, compact = false }: { running?: boolean; compact?: boolean }) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium",
        running
          ? "border-amber-200 bg-amber-50 text-amber-700"
          : "border-emerald-200 bg-emerald-50 text-emerald-700"
      )}
    >
      <span className={cn("h-2 w-2 rounded-full", running ? "bg-amber-500 animate-pulse" : "bg-emerald-500")} />
      {compact ? (running ? "运行中" : "空闲") : running ? "注册任务运行中" : "系统空闲"}
    </div>
  );
}

export function Layout({ jobRunning, onLogout }: { jobRunning?: boolean; onLogout?: () => void }) {
  const location = useLocation();
  const current = nav.find((item) =>
    item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)
  );

  return (
    <div className="min-h-[100dvh] bg-background/70 text-foreground">
      <a
        href="#main-content"
        className="fixed left-3 top-3 z-[100] -translate-y-24 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-transform focus:translate-y-0"
      >
        跳到主要内容
      </a>

      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r bg-card px-4 py-5 lg:flex">
        <div className="mb-7 flex items-center gap-3 px-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <Sparkles className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold tracking-wide">Grok Register</div>
            <div className="text-xs text-muted-foreground">CPA 账号控制台</div>
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-1" aria-label="主导航">
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )
                }
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="mt-5 rounded-2xl border bg-muted/45 p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <span className="text-xs font-medium text-muted-foreground">任务状态</span>
            <StatusPill running={jobRunning} compact />
          </div>
          <div className="flex items-center gap-2 text-xs leading-5 text-muted-foreground">
            <Database className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            本地 SQLite · 轻量 Web
          </div>
          {onLogout ? (
            <button
              type="button"
              onClick={onLogout}
              className="mt-3 flex min-h-9 w-full items-center justify-center gap-2 rounded-lg border bg-card px-3 text-xs font-medium text-foreground hover:bg-muted"
            >
              <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
              退出登录
            </button>
          ) : null}
        </div>
      </aside>

      <div className="min-w-0 lg:pl-64">
        <header className="sticky top-0 z-30 flex min-h-16 items-center justify-between gap-3 border-b bg-card/95 px-4 backdrop-blur lg:hidden">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <Sparkles className="h-4 w-4" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">注册控制台</div>
              <div className="truncate text-xs text-muted-foreground">{current?.label || "工作台"}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusPill running={jobRunning} compact />
            {onLogout ? (
              <button
                type="button"
                onClick={onLogout}
                className="flex h-9 w-9 items-center justify-center rounded-lg border bg-card"
                aria-label="退出登录"
              >
                <LogOut className="h-4 w-4" aria-hidden="true" />
              </button>
            ) : null}
          </div>
        </header>

        <header className="sticky top-0 z-30 hidden min-h-16 items-center justify-between border-b bg-card/90 px-6 backdrop-blur lg:flex">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>工作台</span>
            <span>/</span>
            <span className="font-medium text-foreground">{current?.label || "仪表盘"}</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-xs text-muted-foreground">
              <CircleDot className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
              SQLite 已连接
            </div>
            <StatusPill running={jobRunning} />
            {onLogout ? (
              <button
                type="button"
                onClick={onLogout}
                className="flex min-h-9 items-center gap-2 rounded-lg border bg-card px-3 text-xs font-medium hover:bg-muted"
              >
                <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
                退出
              </button>
            ) : null}
          </div>
        </header>

        <main
          id="main-content"
          className="mx-auto w-full max-w-[1920px] px-4 pb-[calc(6rem+env(safe-area-inset-bottom))] pt-5 sm:px-6 sm:pt-6 lg:px-6 lg:pb-10 lg:pt-8"
        >
          <Outlet />
        </main>
      </div>

      <nav
        className="fixed inset-x-0 bottom-0 z-50 grid grid-cols-4 border-t bg-card/95 px-1 pb-[env(safe-area-inset-bottom)] shadow-[0_-8px_30px_-20px_rgba(15,23,42,0.35)] backdrop-blur lg:hidden"
        aria-label="手机端主导航"
      >
        {nav.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "relative flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-xl px-1 text-[11px] font-medium transition-colors",
                  isActive ? "text-primary" : "text-muted-foreground active:bg-muted"
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={cn(
                      "flex h-8 min-w-12 items-center justify-center rounded-full transition-colors",
                      isActive && "bg-blue-50"
                    )}
                  >
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <span>{item.shortLabel}</span>
                </>
              )}
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
