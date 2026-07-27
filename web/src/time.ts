export const CHINA_TIME_ZONE = "Asia/Shanghai";

export function parseBackendTime(value: string | Date): Date {
  if (value instanceof Date) return value;
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  return new Date(normalized);
}

export function formatChinaTime(value: string | Date): string {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: CHINA_TIME_ZONE,
    dateStyle: "medium",
    timeStyle: "medium",
    hour12: false,
  }).format(parseBackendTime(value));
}

export function chinaInputToIso(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("请输入有效的北京时间。");
  const [, year, month, day, hour, minute] = match;
  return new Date(Date.UTC(
    Number(year), Number(month) - 1, Number(day), Number(hour) - 8, Number(minute),
  )).toISOString();
}

export function isoToChinaInput(value: string | Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: CHINA_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(parseBackendTime(value));
  const item = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find(part => part.type === type)?.value ?? "";
  return `${item("year")}-${item("month")}-${item("day")}T${item("hour")}:${item("minute")}`;
}
