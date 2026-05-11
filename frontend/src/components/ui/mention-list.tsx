'use client';

import React, {
    forwardRef,
    useEffect,
    useImperativeHandle,
    useState,
} from 'react';
import { getAvatarUrl } from '@/lib/utils';

export interface MentionSuggestionItem {
    id: string;
    username: string;
    full_name?: string | null;
    profile_photo?: string | null;
}

export interface MentionListProps {
    items: MentionSuggestionItem[];
    command: (item: { id: string; label: string }) => void;
}

export interface MentionListRef {
    onKeyDown: (props: { event: KeyboardEvent }) => boolean;
}

const MentionList = forwardRef<MentionListRef, MentionListProps>(
    (props, ref) => {
        const [selectedIndex, setSelectedIndex] = useState(0);

        const selectItem = (index: number) => {
            const item = props.items[index];
            if (item) {
                props.command({ id: item.id, label: item.username });
            }
        };

        useEffect(() => setSelectedIndex(0), [props.items]);

        useImperativeHandle(ref, () => ({
            onKeyDown: ({ event }: { event: KeyboardEvent }) => {
                if (event.key === 'ArrowUp') {
                    setSelectedIndex((prev) =>
                        (prev + props.items.length - 1) % props.items.length
                    );
                    return true;
                }
                if (event.key === 'ArrowDown') {
                    setSelectedIndex((prev) =>
                        (prev + 1) % props.items.length
                    );
                    return true;
                }
                if (event.key === 'Enter') {
                    selectItem(selectedIndex);
                    return true;
                }
                return false;
            },
        }));

        if (props.items.length === 0) {
            return (
                <div className="mention-dropdown bg-slate-900 border border-slate-700 rounded-lg shadow-xl p-2 text-sm text-slate-500">
                    No users found
                </div>
            );
        }

        return (
            <div className="mention-dropdown bg-slate-900 border border-slate-700 rounded-lg shadow-xl overflow-hidden max-h-60 overflow-y-auto">
                {props.items.map((item, index) => (
                    <button
                        key={item.id}
                        onClick={() => selectItem(index)}
                        className={`flex items-center gap-2 w-full text-left px-3 py-2 text-sm transition-colors ${index === selectedIndex
                            ? 'bg-teal-500/20 text-white'
                            : 'text-slate-300 hover:bg-slate-800'
                            }`}
                    >
                        {item.profile_photo ? (
                            <img
                                src={getAvatarUrl(item.profile_photo)}
                                alt={item.username}
                                className="h-6 w-6 rounded-full object-cover shrink-0"
                            />
                        ) : (
                            <div className="h-6 w-6 rounded-full bg-teal-600 flex items-center justify-center text-white text-xs font-semibold shrink-0">
                                {item.username.charAt(0).toUpperCase()}
                            </div>
                        )}
                        <div className="flex flex-col min-w-0">
                            <span className="font-medium truncate">
                                {item.username}
                            </span>
                            {item.full_name && (
                                <span className="text-xs text-slate-500 truncate">
                                    {item.full_name}
                                </span>
                            )}
                        </div>
                    </button>
                ))}
            </div>
        );
    }
);

MentionList.displayName = 'MentionList';

export default MentionList;
