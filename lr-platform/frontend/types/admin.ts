export type Id = string | number;

export type ApiResult<T = unknown> = T & {
  success?: boolean;
  message?: string;
  error?: string;
};

export type User = {
  id: Id;
  username: string;
  email?: string;
  role?: string;
  is_active?: boolean;
  last_login_at?: string | null;
  created_at?: string | null;
  windows_username?: string | null;
  windows_domain?: string | null;
  windows_account_enabled?: boolean;
  windows_account_configured?: boolean;
};

export type Server = {
  id: Id;
  name: string;
  host: string;
  ip_address?: string;
  username?: string;
  port?: number;
  agent_id?: string;
  rds_collection_name?: string;
  rds_connection_broker?: string;
  status?: string;
};

export type Application = {
  id: Id;
  name: string;
  description?: string;
  server_id?: Id;
  server_name?: string;
  item_type?: "remote_app" | "folder" | "desktop" | string;
  display_mode?: "full_desktop" | "remote_app" | "seamless" | "html5" | string;
  target?: string;
  
  _program?: string;
  folder_path?: string;
  folder_permission?: string;
  working_directory?: string;
  arguments?: string;
  launch_mode?: string;
  remote_app_alias?: string;
  remote_app_program?: string;
  remote_app_file_path?: string;
  initial_program?: string;
  rds_collection_name?: string;
  rds_connection_broker?: string;
  remote_app_publish_status?: "pending" | "published" | "failed" | "unpublished";
  remote_app_publish_message?: string;
  assigned_users?: User[];
};

export type Assignment = {
  app_id: Id;
  user_id: Id;
};

export type Session = {
  id: Id;
  user_id?: Id;
  username?: string;
  app_name?: string;
  application_name?: string;
  server_name?: string;
  status?: string;
  reconnect_available?: boolean;
  launch_url?: string | null;
  rdp_file_url?: string | null;
  windows_username?: string | null;
  session_isolation?: string;
  is_isolated_session?: boolean;
  started_at?: string | null;
  ended_at?: string | null;
};

export type SessionStats = {
  active?: number;
  total?: number;
};

export type Agent = {
  agent_id: string;
  hostname?: string;
  username?: string;
  status?: string;
  last_seen?: string | null;
  recording?: boolean;
};

export type Monitoring = {
  health?: Record<string, unknown>;
  docker?: {
    containers?: Array<Record<string, unknown>>;
  };
  kubernetes?: {
    pods?: Array<Record<string, unknown>>;
  };
};

export type Transfer = {
  id?: Id;
  filename?: string;
  original_name?: string;
  username?: string;
  size?: number;
  uploaded_at?: string | null;
};

export type Ticket = {
  id: Id;
  username?: string;
  title?: string;
  priority?: string;
  description?: string;
  subject?: string;
  message?: string;
  status?: string;
  created_at?: string | null;
};

export type ClipboardItem = {
  id?: Id;
  username?: string;
  content?: string;
  created_at?: string | null;
};

export type AuditLog = {
  id?: Id;
  username?: string;
  action?: string;
  ip_address?: string;
  created_at?: string | null;
};

export type LoginLink = {
  id: Id;
  username?: string;
  url?: string;
  expires_at?: string | null;
  revoked?: boolean;
};

export type ErrorLog = {
  id?: Id;
  level?: string;
  message?: string;
  created_at?: string | null;
};

export type LicenseInfo = {
  plan?: string;
  status?: string;
  seats?: number;
  used_seats?: number;
  expires_at?: string | null;
  key?: string;
};

export type UserLicenseStatus = {
  status?: "LICENSED" | "TRIAL_ACTIVE" | "TRIAL_EXPIRED" | "HELD" | "NOT_FOUND" | string;
  blocked?: boolean;
  expires_at?: string | null;
  days_remaining?: number | null;
  plan_name?: string | null;
  message?: string;
  trial_days?: number;
};

export type PortalUser = {
  username: string;
  role?: string;
  is_admin?: boolean;
};

export type PortalServer = {
  id: Id;
  name: string;
  ip_address?: string;
  host?: string;
  connection_type?: "rdp" | "ssh" | "vnc" | string;
  os_type?: string;
  rdp_port?: number;
  port?: number;
  description?: string;
  is_active?: boolean;
};

export type PortalApp = {
  id: Id;
  name: string;
  icon?: string;
  description?: string;
  item_type?: string;
  display_mode?: string;
  launch_mode?: string;
  folder_path?: string;
  folder_permission?: string;
};

export type PortalSession = {
  id: Id;
  server_name?: string;
  app_name?: string;
  application_name?: string;
  connection_type?: string;
  status?: string;
  reconnect_available?: boolean;
  windows_username?: string | null;
  session_isolation?: string;
  is_isolated_session?: boolean;
  started_at?: string | null;
  ended_at?: string | null;
  duration_seconds?: number;
};
