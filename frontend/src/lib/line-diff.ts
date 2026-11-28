/**
 * Compute a simple line diff between two strings.
 * Returns arrays of { type, text } where type is 'add', 'remove', or 'same'.
 */
export function computeLineDiff(oldText: string, newText: string) {
    const oldLines = (oldText || '').split('\n');
    const newLines = (newText || '').split('\n');

    // Simple LCS-based diff
    const m = oldLines.length;
    const n = newLines.length;

    // For very long texts, just show full old/new
    if (m + n > 500) {
        return [
            ...oldLines.map(l => ({ type: 'remove' as const, text: l })),
            ...newLines.map(l => ({ type: 'add' as const, text: l })),
        ];
    }

    // Build LCS table
    const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            dp[i][j] = oldLines[i - 1] === newLines[j - 1]
                ? dp[i - 1][j - 1] + 1
                : Math.max(dp[i - 1][j], dp[i][j - 1]);
        }
    }

    // Backtrack
    const result: { type: 'add' | 'remove' | 'same'; text: string }[] = [];
    let i = m, j = n;
    const stack: typeof result = [];
    while (i > 0 || j > 0) {
        if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
            stack.push({ type: 'same', text: oldLines[i - 1] });
            i--; j--;
        } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
            stack.push({ type: 'add', text: newLines[j - 1] });
            j--;
        } else {
            stack.push({ type: 'remove', text: oldLines[i - 1] });
            i--;
        }
    }
    stack.reverse();
    return stack;
}
