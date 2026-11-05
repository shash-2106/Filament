import React, { createContext, useContext, useState } from 'react';
import { getStoredApiKey, setStoredApiKey } from '../api/client';
import { useCurrentWorkspaceQuery } from '../api/queries';

interface WorkspaceContextType {
  apiKey: string;
  setApiKey: (key: string) => void;
  workspaceId: string;
  workspaceName: string;
  workspaceSlug: string;
  currentAgentName?: string;
  currentAgentId?: string;
  isConfigured: boolean;
  isLoading: boolean;
}

const AuthContext = createContext<WorkspaceContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [apiKey, setApiKeyState] = useState<string>(() => {
    return getStoredApiKey();
  });

  const handleSetApiKey = (key: string) => {
    setStoredApiKey(key);
    setApiKeyState(key.trim());
  };

  const { data: wsDetail, isLoading } = useCurrentWorkspaceQuery();

  return (
    <AuthContext.Provider
      value={{
        apiKey,
        setApiKey: handleSetApiKey,
        workspaceId: wsDetail?.id || '',
        workspaceName: wsDetail?.name || 'Workspace Disconnected',
        workspaceSlug: wsDetail?.slug || 'none',
        currentAgentName: wsDetail?.current_agent?.name,
        currentAgentId: wsDetail?.current_agent?.id,
        isConfigured: Boolean(apiKey),
        isLoading,
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
