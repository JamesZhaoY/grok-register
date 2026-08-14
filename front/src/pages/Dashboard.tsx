import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Database,
  Play,
  PlayCircle,
  RefreshCw,
  ServerCog,
  ShieldCheck,
  Users,
} from "lucide-react";
import { api, type JobStatus, type Stats } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  PageHeader,
  StatCard,
  buttonVariants,
} from "@/components/ui";

export function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = async (showRefreshState = false) => {
    if (showRefreshState) setRefreshing(true);
    try {
      const data = await api.stats();
      setStats(data.stats);
      setJob(data.job);
      setError("");
    } catch (err: any) {
      setError(err.message || "加载失败");
    } finally {
      setLoading(false);
      if (showRefreshState) setRefreshing(false);
    }
  };

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 4000);
    return () => window.clearInterval(timer);
  }, []);

  const maxProviderTotal = useMemo(
    () => Math.max(1, ...(stats?.providers || []).map((item) => item.total || 0)),
    [stats?.providers]
  );

  return (
    <div className="space-y-5 sm:space-y-6">
      <PageHeader
        title="仪表盘"
        description="查看注册结果、任务状态与服务商概况，数据实时同步自本地 SQLite。"
        actions={
          <>
            <Button variant="outline" onClick={() => refresh(true)} disabled={refreshing}>
              <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} aria-hidden="true" />
              刷新
            </Button>
            <Link to="/register" className={buttonVariants()}>
              <Play className="h-4 w-4" aria-hidden="true" />
              启动注册
            </Link>
          </>
        }
      />

      {error ? (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="p-4 text-sm text-red-800">{error}</CardContent>
        </Card>
      ) : null}

      <section className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4" aria-label="核心统计">
        <StatCard
          title="成功账号"
          value={loading ? "…" : stats?.unique_success_emails ?? 0}
          hint={`成功记录 ${stats?.success ?? 0} 条`}
          accent="success"
          icon={<CheckCircle2 className="h-4 w-4" aria-hidden="true" />}
        />
        <StatCard
          title="总记录"
          value={loading ? "…" : stats?.total ?? 0}
          hint={`失败 ${stats?.failure ?? 0} · 跳过 ${stats?.skipped ?? 0}`}
          accent="primary"
          icon={<Database className="h-4 w-4" aria-hidden="true" />}
        />
        <StatCard
          title="今日成功"
          value={loading ? "…" : stats?.today_success ?? 0}
          hint={`今日总计 ${stats?.today_total ?? 0}`}
          accent="secondary"
          icon={<Users className="h-4 w-4" aria-hidden="true" />}
        />
        <StatCard
          title="CPA 入库"
          value={loading ? "…" : stats?.cpa_success ?? 0}
          hint={`失败 ${stats?.cpa_failed ?? 0} · 邮箱停用 ${stats?.email_disabled ?? 0}/${(stats?.email_disabled ?? 0) + (stats?.email_disable_failed ?? 0)}`}
          accent="warning"
          icon={<ShieldCheck className="h-4 w-4" aria-hidden="true" />}
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(300px,0.8fr)]">
        <Card>
          <CardHeader className="flex-row items-start justify-between gap-4">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-primary" aria-hidden="true" />
                当前任务
              </CardTitle>
              <CardDescription>注册与 auth 转换共用同一套执行流程。</CardDescription>
            </div>
            <Badge variant={job?.running ? "warning" : "success"}>
              {job?.running ? "运行中" : "空闲"}
            </Badge>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-3 gap-2 sm:gap-3">
              {[
                ["目标数量", job?.target_count ?? 0],
                ["并发数", job?.workers ?? 1],
                ["日志行", job?.log_count ?? 0],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border bg-muted/45 px-3 py-3">
                  <div className="text-xs text-muted-foreground">{label}</div>
                  <div className="mt-1 text-lg font-semibold tabular-nums text-foreground">{value}</div>
                </div>
              ))}
            </div>

            {job?.last_error ? (
              <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-3 text-sm leading-6 text-red-800">
                {job.last_error}
              </div>
            ) : (
              <div className="flex items-start gap-3 rounded-xl border border-blue-100 bg-blue-50/70 px-3 py-3 text-sm leading-6 text-blue-800">
                <Clock3 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>
                  {job?.running
                    ? "任务正在执行，可前往注册台查看实时日志或停止任务。"
                    : "当前没有运行中的注册任务，可随时创建一项新任务。"}
                </span>
              </div>
            )}

            <div className="grid grid-cols-2 gap-2 sm:flex">
              <Link to="/register" className={buttonVariants({ variant: "secondary", className: "w-full sm:w-auto" })}>
                打开注册台
              </Link>
              <Link to="/accounts" className={buttonVariants({ variant: "outline", className: "w-full sm:w-auto" })}>
                管理账号
              </Link>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ServerCog className="h-4 w-4 text-primary" aria-hidden="true" />
              服务商分布
            </CardTitle>
            <CardDescription>成功数 / 总记录数</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {(stats?.providers || []).length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">暂无统计数据</p>
            ) : (
              (stats?.providers || []).slice(0, 6).map((item) => (
                <div key={item.provider || "unknown"} className="space-y-2">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="truncate font-medium text-foreground">{item.provider || "未知"}</span>
                    <span className="shrink-0 tabular-nums text-muted-foreground">
                      <strong className="font-semibold text-emerald-700">{item.success}</strong> / {item.total}
                    </span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-primary transition-[width] duration-300"
                      style={{ width: `${Math.max(5, (item.total / maxProviderTotal) * 100)}%` }}
                    />
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>快速入口</CardTitle>
          <CardDescription>常用工作流可从这里直接进入。</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          {[
            { to: "/register", title: "启动注册", desc: "设置数量与并发，实时查看日志", icon: PlayCircle },
            { to: "/accounts", title: "账号列表", desc: "筛选、查看、复制与批量管理", icon: Users },
            { to: "/settings", title: "系统设置", desc: "维护服务商、代理与 CPA 配置", icon: ServerCog },
          ].map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                className="group flex min-h-24 items-center gap-3 rounded-xl border bg-card p-4 transition-colors hover:border-blue-200 hover:bg-blue-50/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-primary">
                  <Icon className="h-5 w-5" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block font-medium text-foreground">{item.title}</span>
                  <span className="mt-0.5 block text-sm leading-5 text-muted-foreground">{item.desc}</span>
                </span>
                <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" aria-hidden="true" />
              </Link>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
