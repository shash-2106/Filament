import React, { createContext, useContext, useState, useEffect } from 'react';
import { getStoredApiKey, setStoredApiKey } from '../api/client';

interface WorkspaceContextType {
  apiKey: string;
  setApiKey: (key: string) => void;
  workspaceId: string;
  workspaceName: string;
  workspaceSlug: string;
  setWorkspace: (ws: { id: string; name: string; slug: string }) => void;
  isConfigured: boolean;
}

const defaultWorkspace = {
  id: '00000000-0000-0000-0000-000000000001',
  name: 'Default Workspace',
  slug: 'default-workspace',
};

const AuthContext = createContext<WorkspaceContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [apiKey, setApiKeyState] = useState<string>(getStoredApiKey());
  const [workspace, setWorkspace] = useState(defaultWorkspace);

  useEffect(() => {
    // If not set, check if an agent key was stored
    const existing = getStoredApiKey();
    if (existing) {
      setApiKeyState(existing);
    }
  }, []);

  const handleSetApiKey = (key: string) => {
    setStoredApiKey(key);
    setApiKeyState(key.trim());
  };

  return (
    <AuthContext.Provider
      value={{
        apiKey,
        setApiKey: handleSetApiKey,
        workspaceId: workspace.id,
        workspaceName: workspace.name,
        workspaceSlug: workspace.slug,
        setWorkspace,
        isConfigured: Boolean(apiKey),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

