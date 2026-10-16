// State shared between views.
export const SEVERITIES = ["Critical", "Major", "Minor"];
export const DEFAULT_FILTERS = { severity: "", status: "", date_from: "", date_to: "", sort: "inspection_date:desc" };
export const filters = { ...DEFAULT_FILTERS };
export const resetFilters = (overrides = {}) => Object.assign(filters, DEFAULT_FILTERS, overrides);
