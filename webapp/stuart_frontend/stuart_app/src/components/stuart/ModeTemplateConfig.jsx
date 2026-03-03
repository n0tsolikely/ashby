// Canonical Stuart mode + template configuration.
export const MODES = {
  meeting: {
    label: "Meeting",
    description: "Multi-speaker meeting minutes and actions",
    templates: {
      default: {
        label: "Default",
      },
    },
  },
  journal: {
    label: "Journal",
    description: "Single-speaker reflective notes",
    templates: {
      default: {
        label: "Default",
      },
    },
  },
};

export const RETENTION_LEVELS = {
  LOW: {
    label: "Low",
    description: "Highly condensed, key points only"
  },
  MED: {
    label: "Medium",
    description: "Balanced summary with context"
  },
  HIGH: {
    label: "High",
    description: "Detailed preservation of content"
  },
  NEAR_VERBATIM: {
    label: "Near Verbatim",
    description: "Preserve original phrasing as much as possible"
  }
};

export const PROFILES = {
  LOCAL_ONLY: {
    label: "Local Only",
    description: "No data leaves your machine",
    color: "bg-green-500",
    supported: true,
  },
  HYBRID: {
    label: "Hybrid",
    description: "Remote processing with confirmation",
    color: "bg-yellow-500",
    supported: true,
  },
  CLOUD: {
    label: "Cloud",
    description: "Remote-first processing",
    color: "bg-blue-500",
    supported: false,
  },
};

function normalizeRegistryTemplates(mode, templatesByMode) {
  const rows = templatesByMode?.[mode];
  if (!Array.isArray(rows) || rows.length === 0) return {};
  const out = {};
  rows.forEach((row) => {
    const templateId = String(row?.template_id || '').trim();
    if (!templateId) return;
    out[templateId] = {
      label: String(row?.template_title || templateId),
      template_id: templateId,
      template_title: String(row?.template_title || templateId),
      template_version: String(row?.template_version || '1'),
      source: String(row?.source || 'system'),
    };
  });
  return out;
}

export function getTemplatesForMode(mode, templatesByMode = null) {
  const fromRegistry = normalizeRegistryTemplates(mode, templatesByMode);
  if (Object.keys(fromRegistry).length > 0) return fromRegistry;
  return MODES[mode]?.templates || {};
}

export function isValidModeTemplate(mode, template, templatesByMode = null) {
  return getTemplatesForMode(mode, templatesByMode)[template] !== undefined;
}
