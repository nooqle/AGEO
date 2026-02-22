export interface Session {
  id: string;
  createdAt: Date;
  updatedAt: Date;
  brandName?: string;
  status: 'active' | 'archived';
}

export interface SessionCreate {
  brandName?: string;
}

export interface SessionListItem {
  id: string;
  title: string | null;
  status: string;
  brand_name: string | null;
  entity_id: string | null;
  last_message_preview: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface SessionListResponse {
  sessions: SessionListItem[];
  total: number;
}
