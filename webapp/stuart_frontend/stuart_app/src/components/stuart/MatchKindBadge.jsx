import React from 'react';
import { Badge } from '@/components/ui/badge';
import { FileText, Hash, User } from 'lucide-react';

export function MatchKindBadge({ kind }) {
  const v = String(kind || '').toUpperCase();
  if (v === 'TITLE_MATCH') return <Badge variant="outline">Title</Badge>;
  if (v === 'ID_MATCH') {
    return (
      <Badge variant="outline">
        <Hash className="h-3 w-3 mr-1" />
        ID
      </Badge>
    );
  }
  if (v === 'ATTENDEE_MATCH') {
    return (
      <Badge variant="outline">
        <User className="h-3 w-3 mr-1" />
        Attendee
      </Badge>
    );
  }
  if (v === 'MENTION_MATCH') {
    return (
      <Badge variant="outline">
        <FileText className="h-3 w-3 mr-1" />
        Mentioned
      </Badge>
    );
  }
  return null;
}
