import { requestOperation } from './operations';

export const getAiQualitySummary = (days = 30) =>
    requestOperation('getAiQualitySummary', { params: { days } });

export const listAiInvocations = (params = {}) =>
    requestOperation('listAiInvocations', { params });

export const listAiEvaluationCases = (enabled) =>
    requestOperation('listAiEvaluationCases', { params: { enabled } });

export const createAiEvaluationCase = (data) =>
    requestOperation('createAiEvaluationCase', { data });

export const updateAiEvaluationCase = (caseId, data) =>
    requestOperation('updateAiEvaluationCase', { path: { caseId }, data });

export const runAiEvaluation = (data = {}) =>
    requestOperation('runAiEvaluation', { data });

export const listAiEvaluationRuns = (params = {}) =>
    requestOperation('listAiEvaluationRuns', { params });
