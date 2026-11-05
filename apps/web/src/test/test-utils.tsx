import React, { ReactElement } from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/auth';

export const createTestQueryClient = () => {
  const qc = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
      },
      mutations: {
        retry: false,
      },
    },
  });
  // Set default mock workspace so UI components receive standard workspace identity
  qc.setQueryData(['workspace', 'current'], {
    id: '00000000-0000-0000-0000-000000000001',
    name: 'Default Workspace',
    slug: 'default-workspace',
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
    current_agent: {
      id: '00000000-0000-0000-0000-000000000002',
      workspace_id: '00000000-0000-0000-0000-000000000001',
      name: 'Default Test Agent',
      default_scope: 'team',
      is_active: true,
      created_at: '2026-11-01T00:00:00Z',
      updated_at: '2026-11-01T00:00:00Z',
    },
  });
  return qc;
};

interface ExtendedRenderOptions extends Omit<RenderOptions, 'queries'> {
  route?: string;
  queryClient?: QueryClient;
  apiKey?: string;
}

export function renderWithProviders(
  ui: ReactElement,
  {
    route = '/',
    queryClient = createTestQueryClient(),
    apiKey = 'fil_test_key_123',
    ...renderOptions
  }: ExtendedRenderOptions = {}
) {
  if (apiKey !== undefined) {
    if (apiKey) {
      localStorage.setItem('filament_api_key', apiKey);
    } else {
      localStorage.setItem('filament_api_key', '');
    }
  } else {
    localStorage.removeItem('filament_api_key');
  }

  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <MemoryRouter initialEntries={[route]}>
            {children}
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>
    );
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    queryClient,
  };
}
