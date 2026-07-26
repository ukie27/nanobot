import { cli, Strategy } from '@jackwener/opencli/registry';

const API_URL = 'https://www.nowcoder.com/np-api/u/school-schedule/list-card';
const PAGE_SIZE = 50;
const MAX_PAGES = 20;
const ALLOWED_LOOKBACK_DAYS = new Set([0, 7, 14, 30]);
const CHINA_TIME_ZONE = 'Asia/Shanghai';

function integer(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function chinaDateParts(value = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: CHINA_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(value);
  const get = (type) => parts.find((part) => part.type === type)?.value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}

function dateWindow(lookbackDays) {
  const today = chinaDateParts();
  const todayStart = Date.parse(`${today}T00:00:00+08:00`);
  const calendarDays = lookbackDays === 0 ? 1 : lookbackDays;
  return {
    start: todayStart - (calendarDays - 1) * 86_400_000,
    end: todayStart + 86_400_000,
  };
}

async function fetchPage({ tab, page, query }) {
  const response = await fetch(API_URL, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      Referer: 'https://www.nowcoder.com/jobs/school/schedule',
    },
    body: JSON.stringify({
      tab,
      page,
      pageSize: PAGE_SIZE,
      query,
      propertyId: '',
    }),
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) {
    throw new Error(`Nowcoder schedule request failed with HTTP ${response.status}`);
  }
  const payload = await response.json();
  if (payload?.code !== 0 || !payload?.data || !Array.isArray(payload.data.datas)) {
    throw new Error(`Nowcoder schedule returned an invalid response: ${payload?.msg || 'unknown'}`);
  }
  return payload.data;
}

function scheduleId(item) {
  return [
    item.companyId,
    item.batch ?? 'unknown',
    item.wangshenBeginDate ?? 'unknown',
  ].join(':');
}

function normalize(item) {
  const companyUrl = `https://www.nowcoder.com/enterprise/${item.companyId}`
    + '?pageSource=5014&channel=recruitmentSchedule';
  const collectedTime = Number(item.wangshenUpdateTime || item.updateTime || 0);
  const updateTime = Number(item.updateTime || item.wangshenUpdateTime || 0);
  return {
    id: scheduleId(item),
    company_id: String(item.companyId),
    company: String(item.name || '').trim(),
    batch: String(item.batchName || '').trim(),
    cities: Array.isArray(item.cityList) ? item.cityList.join(',') : '',
    careers: Array.isArray(item.careerNameList) ? item.careerNameList.join(',') : '',
    industries: Array.isArray(item.industryList) ? item.industryList.join(',') : '',
    evaluation: String(item.companyEvaluation || '').trim(),
    collected_label: item.cardSchoolScheduleInfo?.content?.data?.[2]?.text || '',
    collected_at: collectedTime ? new Date(collectedTime).toISOString() : '',
    updated_at: updateTime ? new Date(updateTime).toISOString() : '',
    application_starts_at: item.wangshenBeginDate
      ? new Date(item.wangshenBeginDate).toISOString()
      : '',
    application_ends_at: item.wangshenEndDate
      ? new Date(item.wangshenEndDate).toISOString()
      : '',
    source_url: companyUrl,
    announcement_url: String(item.sourceInformation || '').trim(),
    application_url: String(
      item.customWangshenLink || item.adInfo?.rawUrl || item.sourceInformation || companyUrl,
    ).trim(),
  };
}

cli({
  site: 'nowcoder',
  name: 'schedule',
  access: 'read',
  description: 'Latest campus recruitment schedules with China-calendar date filtering',
  example: 'opencli nowcoder schedule --lookback 0 --limit 500 -f json',
  domain: 'www.nowcoder.com',
  strategy: Strategy.PUBLIC,
  browser: false,
  args: [
    {
      name: 'lookback',
      type: 'int',
      default: 0,
      help: 'China-calendar lookback: 0=today; manual history supports 7, 14, or 30 days',
    },
    { name: 'limit', type: 'int', default: 500, help: 'Maximum rows (1-1000)' },
    { name: 'query', type: 'str', default: '', help: 'Optional company keyword' },
  ],
  columns: [
    'id',
    'company',
    'batch',
    'cities',
    'careers',
    'industries',
    'collected_label',
    'collected_at',
    'updated_at',
    'application_url',
    'source_url',
  ],
  validateArgs: (args) => {
    const lookback = integer(args.lookback, 0);
    if (!ALLOWED_LOOKBACK_DAYS.has(lookback)) {
      throw new Error('--lookback must be one of: 0, 7, 14, 30');
    }
    const limit = integer(args.limit, 500);
    if (limit < 1 || limit > 1000) {
      throw new Error('--limit must be between 1 and 1000');
    }
  },
  func: async (args) => {
    const lookback = integer(args.lookback, 0);
    const limit = integer(args.limit, 500);
    const query = String(args.query || '').trim();
    const window = dateWindow(lookback);
    const tab = lookback === 0 ? 3 : 0;
    const rows = [];

    for (let page = 1; page <= MAX_PAGES && rows.length < limit; page += 1) {
      const result = await fetchPage({ tab, page, query });
      let newestOnPage = 0;
      for (const item of result.datas) {
        const collectedAt = Number(item.wangshenUpdateTime || item.updateTime || 0);
        newestOnPage = Math.max(newestOnPage, collectedAt);
        if (collectedAt >= window.start && collectedAt < window.end) {
          rows.push(normalize(item));
          if (rows.length >= limit) break;
        }
      }
      if (page >= result.totalPage || (lookback !== 0 && newestOnPage < window.start)) break;
    }
    return rows;
  },
});
