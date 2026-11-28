import type { SectionType } from '@/lib/types';
import type { ReportSectionCreate } from '@/lib/hooks/use-report-layouts';
import type { ReportLayoutTemplateSectionCreate } from '@/lib/hooks/use-report-layout-templates';

/** A report-layout section as the reporting tab edits it in memory. */
export interface LocalSection {
    localId: string; // for dnd-kit key; may not map to a real id
    id?: string;     // server id once saved — keeps review threads attached
    section_type: SectionType;
    title: string;
    content: string;
    classification_level?: string | null;
    classification_suffix?: string | null;
    page_break_before?: boolean;
}

/** The sections a layout save sends: list order becomes sort_order, and
 *  existing sections keep their id so their review threads stay attached. */
export function toSectionPayload(sections: LocalSection[]): ReportSectionCreate[] {
    return sections.map((s, i) => ({
        id: s.id,
        section_type: s.section_type as 'text' | 'findings' | 'testcases' | 'cleanup_artifacts',
        title: s.title,
        content: s.content,
        sort_order: i,
        classification_level: s.classification_level || null,
        classification_suffix: s.classification_suffix || null,
        page_break_before: !!s.page_break_before,
    }));
}

/** The sections a save-as-template sends (no ids or markings). */
export function toTemplateSectionPayload(sections: LocalSection[]): ReportLayoutTemplateSectionCreate[] {
    return sections.map((s, i) => ({
        section_type: s.section_type as 'text' | 'findings' | 'testcases' | 'cleanup_artifacts',
        title: s.title,
        content: s.content,
        sort_order: i,
    }));
}

/** Adopt the server ids from a save response (new sections get one; existing
 *  ones keep theirs), matching by position in sort_order. */
export function adoptSavedSectionIds(
    sections: LocalSection[],
    saved: { id: string; sort_order: number }[],
): LocalSection[] {
    const savedIds = [...saved].sort((a, b) => a.sort_order - b.sort_order).map(s => s.id);
    return sections.map((s, i) => ({ ...s, id: savedIds[i] ?? s.id }));
}
