export function formatTokens(tokens: number | undefined | null): string {
  if (tokens === undefined || tokens === null) return "0";
  return new Intl.NumberFormat('en-US').format(tokens);
}

export function formatDuration(ms: number | undefined | null): string {
  if (ms === undefined || ms === null) return "-";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function formatDate(dateString: string | undefined | null): string {
  if (!dateString) return "-";
  return new Date(dateString).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}
