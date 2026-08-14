import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  CircleOff,
  Loader2,
  Play,
  RotateCcw,
  Square,
  TerminalSquare,
  Wifi,
  XCircle,
} from "lucide-react";
import { api, type JobStatus, type LogItem } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  PageHeader,
  Switch,
  Toast,
} from "@/components/ui";

type BusyAction = "" | "start" | "stop" | "check" | "kill";

// 与后端 engine.MAX_REGISTER_COUNT / MAX_REGISTER_WORKERS 保持一致。
const MAX_REGISTER_COUNT = 100000;
const MAX_REGISTER_WORKERS = 10;

function normalizeInteger(value: string | number, min: number, max: number, fallback = min) {
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

export function RegisterPage() {
  const [count, setCount] = useState("1");
  const [workers, setWorkers] = useState("1");
  const [job, setJob] = useState<JobStatus | null>(null);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [logViewCleared, setLogViewCleared] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [busyAction, setBusyAction] = useState<BusyAction>("");
  const [jobPolling, setJobPolling] = useState(true);
  const [checks, setChecks] = useState<Array<{ name: string; ok: boolean; detail: string }>>([]);
  const [toast, setToast] = useState<{ message: string; tone?: "default" | "success" | "error" }>({
    message: "",
  });
  const logRef = useRef<HTMLDivElement | null>(null);
  const afterIdRef = useRef(0);
  const logViewVersionRef = useRef(0);
  const pollingRef = useRef(false);
  const progressTarget = Math.max(Number(job?.target_count || count || 1), 1);
  const progressCompleted = Math.min(Number(job?.completed_count || 0), progressTarget);
  const progressPercent = Math.min(
    100,
    Math.max(0, Number(job?.progress_percent ?? (progressCompleted / progressTarget) * 100))
  );

  const showToast = (message: string, tone: "default" | "success" | "error" = "default") => {
    setToast({ message, tone });
    window.setTimeout(() => setToast({ message: "" }), 2200);
  };

  const emitJobState = (running: boolean) => {
    window.dispatchEvent(new CustomEvent("grok-job-state", { detail: { running } }));
  };

  const refreshLogs = async (): Promise<JobStatus | null> => {
    if (pollingRef.current) return null;
    pollingRef.current = true;
    const viewVersion = logViewVersionRef.current;
    try {
      const data = await api.logs(afterIdRef.current, 500);
      setJob(data.job);
      // Ignore a response started before the user cleared the local view.
      if (viewVersion !== logViewVersionRef.current) return;
      const freshLogs = (data.logs || []).filter((item) => item.id > afterIdRef.current);
      if (freshLogs.length) {
        setLogs((prev) => [...prev, ...freshLogs].slice(-2000));
        afterIdRef.current = freshLogs[freshLogs.length - 1].id;
        setLogViewCleared(false);
      }
      return data.job;
    } catch {
      // 忽略短暂轮询失败，下一轮继续同步。
      return null;
    } finally {
      pollingRef.current = false;
    }
  };

  useEffect(() => {
    api
      .getConfig()
      .then((data) => {
        setCount(String(normalizeInteger(data.config.register_count || 1, 1, MAX_REGISTER_COUNT)));
        setWorkers(
          String(normalizeInteger(data.config.register_workers || 1, 1, MAX_REGISTER_WORKERS))
        );
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!jobPolling) return;
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      if (cancelled) return;
      const current = await refreshLogs();
      if (cancelled) return;
      if (current?.running) {
        timer = window.setTimeout(tick, 1500);
      } else if (current) {
        setJobPolling(false);
        emitJobState(false);
      } else {
        timer = window.setTimeout(tick, 3000);
      }
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [jobPolling]);

  useEffect(() => {
    if (autoScroll && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const onStart = async () => {
    setBusyAction("start");
    try {
      const normalizedCount = normalizeInteger(count, 1, MAX_REGISTER_COUNT);
      const normalizedWorkers = normalizeInteger(workers, 1, MAX_REGISTER_WORKERS);
      setCount(String(normalizedCount));
      setWorkers(String(normalizedWorkers));
      const data = await api.startJob({ count: normalizedCount, workers: normalizedWorkers });
      setJob(data.job);
      setJobPolling(!!data.job.running);
      emitJobState(!!data.job.running);
      showToast("注册任务已启动", "success");
    } catch (err: any) {
      showToast(err.message || "启动失败", "error");
    } finally {
      setBusyAction("");
    }
  };

  const onStop = async () => {
    setBusyAction("stop");
    try {
      const data = await api.stopJob();
      setJob(data.job);
      setJobPolling(!!data.job.running);
      emitJobState(!!data.job.running);
      showToast("已请求停止", "success");
    } catch (err: any) {
      showToast(err.message || "停止失败", "error");
    } finally {
      setBusyAction("");
    }
  };

  const onCheck = async () => {
    setBusyAction("check");
    try {
      const data = await api.connectivity();
      setChecks(data.items || []);
      showToast(data.blocked ? "目标站点被拦截，请检查代理" : "连通性检查完成", data.blocked ? "error" : "success");
    } catch (err: any) {
      showToast(err.message || "检查失败", "error");
    } finally {
      setBusyAction("");
    }
  };

  const onKillBrowsers = async () => {
    if (!window.confirm("终止所有 Camoufox 浏览器进程？正在运行的注册任务也会先请求停止。")) return;
    setBusyAction("kill");
    try {
      const data = await api.killAllBrowsers();
      setJob(data.job);
      setJobPolling(!!data.job.running);
      emitJobState(!!data.job.running);
      showToast(
        `已终止 ${data.killed} 个进程，清理 ${data.profiles_cleaned} 个资料目录`,
        "success"
      );
    } catch (err: any) {
      showToast(err.message || "终止浏览器失败", "error");
    } finally {
      setBusyAction("");
    }
  };

  const clearLogView = () => {
    const latestId = Math.max(afterIdRef.current, Number(job?.latest_log_id || 0));
    logViewVersionRef.current += 1;
    setLogs([]);
    afterIdRef.current = latestId;
    setLogViewCleared(true);
    showToast(job?.running ? "视图已清空，将继续接收新日志" : "日志视图已清空");
  };

  return (
    <div className="space-y-5 sm:space-y-6">
      <PageHeader
        title="启动注册"
        description="设置本次任务的账号数量与并发，并在任意设备上查看实时执行日志。"
        actions={
          <div className="flex items-center sm:justify-end">
            <Badge variant={job?.running ? "warning" : "success"}>
              {job?.running ? "任务运行中" : "空闲可启动"}
            </Badge>
          </div>
        }
      />

      <div className="grid items-start gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Card className="xl:sticky xl:top-24">
          <CardHeader>
            <CardTitle>任务参数</CardTitle>
            <CardDescription>邮箱、代理和 CPA 入库配置可在系统设置中维护。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="count">注册数量</Label>
                <Input
                  id="count"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={MAX_REGISTER_COUNT}
                  value={count}
                  disabled={!!job?.running}
                  onChange={(e) => setCount(e.target.value)}
                  onBlur={() => setCount(String(normalizeInteger(count, 1, MAX_REGISTER_COUNT)))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="workers">并发数</Label>
                <Input
                  id="workers"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={MAX_REGISTER_WORKERS}
                  value={workers}
                  disabled={!!job?.running}
                  onChange={(e) => setWorkers(e.target.value)}
                  onBlur={() =>
                    setWorkers(String(normalizeInteger(workers, 1, MAX_REGISTER_WORKERS)))
                  }
                />
              </div>
            </div>

            <div className="flex min-h-16 items-center justify-between gap-4 rounded-xl border bg-muted/40 px-3 py-3">
              <div className="min-w-0">
                <div className="text-sm font-medium">日志自动滚动</div>
                <div className="mt-0.5 text-xs leading-5 text-muted-foreground">新日志到达时自动定位到底部</div>
              </div>
              <Switch
                checked={autoScroll}
                onCheckedChange={setAutoScroll}
                label="日志自动滚动"
              />
            </div>

            <div className="space-y-3 rounded-xl border bg-blue-50/60 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-foreground">注册进度</div>
                  <div className="mt-1 truncate text-xs text-muted-foreground" title={job?.current_email || ""}>
                    {job?.current_stage || "等待启动"}
                    {job?.current_email ? ` · ${job.current_email}` : ""}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="text-lg font-semibold tabular-nums text-primary">{Math.round(progressPercent)}%</div>
                  <div className="text-xs tabular-nums text-muted-foreground">{progressCompleted}/{progressTarget}</div>
                </div>
              </div>
              <div
                className="h-2.5 overflow-hidden rounded-full bg-blue-100"
                role="progressbar"
                aria-label="账号注册进度"
                aria-valuemin={0}
                aria-valuemax={progressTarget}
                aria-valuenow={progressCompleted}
              >
                <div
                  className="h-full rounded-full bg-primary transition-[width] duration-500"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-lg bg-card px-2 py-2 text-muted-foreground">
                  已完成 <strong className="block text-sm tabular-nums text-foreground">{progressCompleted}</strong>
                </div>
                <div className="rounded-lg bg-emerald-50 px-2 py-2 text-emerald-700">
                  成功 <strong className="block text-sm tabular-nums">{job?.success_count || 0}</strong>
                </div>
                <div className="rounded-lg bg-red-50 px-2 py-2 text-red-700">
                  失败 <strong className="block text-sm tabular-nums">{job?.failure_count || 0}</strong>
                </div>
              </div>
            </div>

            <Button className="w-full" onClick={onStart} disabled={!!busyAction || !!job?.running}>
              {busyAction === "start" ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Play className="h-4 w-4" aria-hidden="true" />
              )}
              开始注册
            </Button>

            <div className="grid grid-cols-2 gap-2">
              <Button variant="destructive" onClick={onStop} disabled={!!busyAction || !job?.running}>
                {busyAction === "stop" ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Square className="h-4 w-4" aria-hidden="true" />
                )}
                停止
              </Button>
              <Button variant="outline" onClick={onCheck} disabled={!!busyAction}>
                {busyAction === "check" ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Wifi className="h-4 w-4" aria-hidden="true" />
                )}
                连通检查
              </Button>
            </div>

            <Button variant="destructive" className="w-full" onClick={onKillBrowsers} disabled={!!busyAction}>
              {busyAction === "kill" ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <CircleOff className="h-4 w-4" aria-hidden="true" />
              )}
              终止所有 Camoufox
            </Button>

            {checks.length > 0 ? (
              <div className="space-y-2 rounded-xl border bg-muted/35 p-3">
                <div className="text-sm font-medium">最近检查</div>
                {checks.map((item) => (
                  <div key={item.name} className="flex items-start gap-2 text-xs leading-5">
                    {item.ok ? (
                      <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" aria-hidden="true" />
                    ) : (
                      <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600" aria-hidden="true" />
                    )}
                    <span className="break-all text-muted-foreground">
                      <strong className="font-medium text-foreground">{item.name}</strong>：{item.detail}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="min-w-0 overflow-hidden">
          <CardHeader className="flex-row items-start justify-between gap-3">
            <div className="min-w-0">
              <CardTitle className="flex items-center gap-2">
                <TerminalSquare className="h-4 w-4 text-primary" aria-hidden="true" />
                实时日志
              </CardTitle>
              <CardDescription>
                已缓冲 {logs.length} 行{job?.last_error ? ` · 最近错误：${job.last_error}` : ""}
              </CardDescription>
            </div>
            <Button size="sm" variant="outline" onClick={clearLogView} aria-label="清空日志视图">
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">清空视图</span>
            </Button>
          </CardHeader>
          <CardContent className="p-3 pt-1 sm:p-5 sm:pt-2">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-muted/35 px-3 py-2 text-xs text-muted-foreground">
              <span className="flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${job?.running ? "animate-pulse bg-amber-500" : "bg-emerald-500"}`} />
                {job?.running ? "日志持续同步中" : "等待新任务"}
              </span>
              <span className="tabular-nums">目标 {job?.target_count ?? 0} · 并发 {job?.workers ?? 1}</span>
            </div>
            <div
              ref={logRef}
              role="log"
              aria-live="polite"
              className="font-mono-log h-[50dvh] min-h-[360px] max-h-[620px] overflow-auto rounded-xl border bg-slate-50 p-3 text-xs leading-6 text-slate-700 sm:h-[540px] sm:p-4 xl:h-[600px]"
            >
              {logs.length === 0 ? (
                <div className="flex h-full min-h-40 items-center justify-center text-center text-muted-foreground">
                  {job?.running
                    ? logViewCleared
                      ? "视图已清空，正在等待下一条实时日志…"
                      : "任务运行中，正在等待实时日志…"
                    : "等待日志…启动任务后会在这里实时输出。"}
                </div>
              ) : (
                logs.map((item) => (
                  <div key={item.id} className="border-b border-slate-200/60 py-0.5 last:border-0">
                    <span className="text-blue-600">[{item.time}]</span>{" "}
                    <span className="whitespace-pre-wrap break-all">{item.message}</span>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <Toast message={toast.message} tone={toast.tone} />
    </div>
  );
}
