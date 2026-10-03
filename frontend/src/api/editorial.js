import { requestOperation } from './operations';

export const getPublicEvent = (eventId, signal) =>
    requestOperation('getPublicEvent', { path: { eventId }, signal });

export const getEditorialEntry = (entryId) =>
    requestOperation('getEditorialEntry', { path: { entryId } });

export const updateEditorialEntry = (entryId, data) =>
    requestOperation('updateEditorialEntry', { path: { entryId }, data });

export const restoreEditorialRevision = (entryId, revisionNumber) =>
    requestOperation('restoreEditorialRevision', { path: { entryId, revisionNumber } });

export const addEditorialFeedback = (entryId, data) =>
    requestOperation('addEditorialFeedback', { path: { entryId }, data });

export const getEditorialEvent = (eventId) =>
    requestOperation('getEditorialEvent', { path: { eventId } });

export const updateEventSourceEvidence = (eventId, newsId, data) =>
    requestOperation('updateEventSourceEvidence', { path: { eventId, newsId }, data });

export const addEventUpdate = (eventId, data) =>
    requestOperation('addEventUpdate', { path: { eventId }, data });

export const updateEventUpdate = (updateId, data) =>
    requestOperation('updateEventUpdate', { path: { updateId }, data });

export const addEventFact = (eventId, data) =>
    requestOperation('addEventFact', { path: { eventId }, data });

export const updateEventFact = (factId, data) =>
    requestOperation('updateEventFact', { path: { factId }, data });

export const addEventRelation = (eventId, data) =>
    requestOperation('addEventRelation', { path: { eventId }, data });

export const listPublicationDrafts = (params = {}) =>
    requestOperation('listPublicationDrafts', { params });

export const createPublicationDraft = (data) =>
    requestOperation('createPublicationDraft', { data });

export const getPublicationDraft = (draftId) =>
    requestOperation('getPublicationDraft', { path: { draftId } });

export const updatePublicationDraft = (draftId, data) =>
    requestOperation('updatePublicationDraft', { path: { draftId }, data });

export const previewPublicationDraft = (draftId) =>
    requestOperation('previewPublicationDraft', { path: { draftId } });

export const publishPublicationDraft = (draftId, params = {}) =>
    requestOperation('publishPublicationDraft', { path: { draftId }, params });

export const publishDueDrafts = (params = {}) =>
    requestOperation('publishDueDrafts', { params });

export const listPublicationCorrections = (params = {}) =>
    requestOperation('listPublicationCorrections', { params });

export const createPublicationCorrection = (data) =>
    requestOperation('createPublicationCorrection', { data });

export const publishPublicationCorrection = (correctionId) =>
    requestOperation('publishPublicationCorrection', { path: { correctionId } });
