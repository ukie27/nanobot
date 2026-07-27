import { useMutation } from "@tanstack/react-query";

import {
  ApiError,
  testConfigurationCapability,
  type ConfigurationCheckResult,
} from "./api";

const STATUS_LABEL: Record<ConfigurationCheckResult["status"], string> = {
  passed: "测试通过",
  failed: "测试失败",
  blocked: "暂时不可测试",
};

export function ConfigurationTestButton({
  capability,
  label = "测试配置",
  disabled = false,
  onPassed,
}: {
  capability: string;
  label?: string;
  disabled?: boolean;
  onPassed?: (result: ConfigurationCheckResult) => void;
}) {
  const test = useMutation({
    mutationFn: () => testConfigurationCapability(capability),
    onSuccess: result => {
      if (result.status === "passed") onPassed?.(result);
    },
  });
  const result = test.data;
  const error = test.error;

  return <div className="configuration-test">
    <button
      type="button"
      className="secondary"
      disabled={disabled || test.isPending}
      onClick={() => test.mutate()}
    >
      {test.isPending ? "正在测试…" : label}
    </button>
    {result && <div
      className={`test-result ${result.status}`}
      role={result.status === "passed" ? "status" : "alert"}
    >
      <strong>{STATUS_LABEL[result.status]}</strong>
      <span>{result.summary}</span>
      {!!result.details.length && <small>{result.details.join(" · ")}</small>}
      {result.error_code && <details>
        <summary>查看诊断代码</summary>
        <code>{result.error_code}</code>
      </details>}
    </div>}
    {error && <div className="test-result failed" role="alert">
      <strong>测试请求失败</strong>
      <span>{error.message}</span>
      {error instanceof ApiError && error.correlationId && <code>关联 ID：{error.correlationId}</code>}
    </div>}
  </div>;
}
