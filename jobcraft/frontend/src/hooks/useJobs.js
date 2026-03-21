import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api/client';

export function useJobs({ sortBy = 'composite_score', grade, search } = {}) {
  return useQuery({
    queryKey: ['jobs', sortBy, grade, search],
    queryFn: async () => {
      const params = { sort_by: sortBy };
      if (grade) params.grade = grade;
      if (search) params.search = search;
      const { data } = await api.get('/jobs', { params });
      return data;
    },
  });
}

export function useJobDetail(jobId) {
  return useQuery({
    queryKey: ['job', jobId],
    queryFn: async () => {
      const { data } = await api.get(`/jobs/${jobId}`);
      return data;
    },
    enabled: !!jobId,
  });
}

export function useSearchStatus() {
  return useQuery({
    queryKey: ['searchStatus'],
    queryFn: async () => {
      const { data } = await api.get('/search/status');
      return data;
    },
    // Keep polling while the loading screen is open; server state can flip from
    // pending->running very quickly and one missed poll can freeze UI at 10%.
    staleTime: 0,
    refetchOnMount: true,
    refetchOnWindowFocus: true,
    refetchInterval: (data) => (data?.running ? 2000 : false),
    refetchIntervalInBackground: true,
    retry: 10,
    retryDelay: 1500,
  });
}

export function useStartSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload) => {
      const { data } = await api.post('/search/start', payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['searchStatus'] });
    },
  });
}

export function useRegenerateResume() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (jobId) => {
      const { data } = await api.post(`/jobs/${jobId}/regenerate`);
      return data;
    },
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: ['job', jobId] });
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useUploadResume() {
  return useMutation({
    mutationFn: async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      const { data } = await api.post('/resume/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return data;
    },
  });
}

export function useCurrentResume() {
  return useQuery({
    queryKey: ['currentResume'],
    queryFn: async () => {
      const { data } = await api.get('/resume/current');
      return data;
    },
  });
}

export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const { data } = await api.get('/settings');
      return data;
    },
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (settings) => {
      const { data } = await api.put('/settings', settings);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
  });
}

export function useSearchCandidates(runId) {
  return useQuery({
    queryKey: ['searchCandidates', runId],
    queryFn: async () => {
      const { data } = await api.get(`/search/${runId}/candidates`);
      return data;
    },
    enabled: !!runId,
    staleTime: 0,
    refetchInterval: (data) => {
      if (!data) return 2000;
      const st = data.run_status;
      if (st === 'completed' || st === 'failed') return false;
      return 2000;
    },
    retry: 10,
    retryDelay: 1500,
  });
}

export function useProcessSelectedJobs(runId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (jobIds) => {
      const { data } = await api.post(`/search/${runId}/process-selected`, { job_ids: jobIds });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['searchStatus'] });
    },
  });
}
