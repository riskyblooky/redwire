'use client';

/**
 * ColumnToggle — a compact popover listing available columns with checkboxes.
 * Wire into any table header alongside sort/filter controls.
 */
import { Columns3 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover';
import { ColumnDef } from '@/lib/hooks/use-column-visibility';
import { cn } from '@/lib/utils';

interface ColumnToggleProps {
    columns: ColumnDef[];
    visible: Set<string>;
    onToggle: (key: string) => void;
    className?: string;
}

export function ColumnToggle({ columns, visible, onToggle, className }: ColumnToggleProps) {
    const hiddenCount = columns.filter(c => !c.required && !visible.has(c.key)).length;

    return (
        <Popover>
            <PopoverTrigger asChild>
                <Button
                    size="icon"
                    variant="ghost"
                    className={cn('h-9 w-9 relative', hiddenCount > 0 ? 'text-primary' : 'text-slate-400 hover:text-white', className)}
                    title="Toggle columns"
                >
                    <Columns3 className="h-4 w-4" />
                    {hiddenCount > 0 && (
                        <span className="absolute -top-1 -right-1 h-4 min-w-4 rounded-full bg-primary text-[9px] font-bold text-white flex items-center justify-center px-1 leading-none">
                            {hiddenCount}
                        </span>
                    )}
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-52 p-3 bg-slate-900 border-slate-700" align="end">
                <p className="text-[10px] uppercase tracking-wider text-slate-500 font-medium mb-2">
                    Columns
                </p>
                <div className="space-y-1">
                    {columns.map(col => (
                        <label
                            key={col.key}
                            className={cn(
                                'flex items-center gap-2.5 py-1 cursor-pointer',
                                col.required && 'opacity-50 cursor-not-allowed',
                            )}
                        >
                            <Checkbox
                                checked={visible.has(col.key)}
                                disabled={col.required}
                                onCheckedChange={() => onToggle(col.key)}
                            />
                            <span className="text-sm text-slate-200">{col.label}</span>
                        </label>
                    ))}
                </div>
            </PopoverContent>
        </Popover>
    );
}
