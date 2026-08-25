import { requestOperation } from './operations';

export const listPublications = () => requestOperation('listPublications');
export const updatePublication = (publicationId, data) => requestOperation('updatePublication', { path: { publicationId }, data });
export const listPublicationChannels = () => requestOperation('listPublicationChannels');
export const createPublicationChannel = (data) => requestOperation('createPublicationChannel', { data });
export const updatePublicationChannel = (channelId, data) => requestOperation('updatePublicationChannel', { path: { channelId }, data });
export const testPublicationChannel = (channelId) => requestOperation('testPublicationChannel', { path: { channelId } });
export const listAnalystSubscriptions = () => requestOperation('listAnalystSubscriptions');
export const createAnalystSubscription = (data) => requestOperation('createAnalystSubscription', { data });
export const updateAnalystSubscription = (subscriptionId, data) => requestOperation('updateAnalystSubscription', { path: { subscriptionId }, data });
export const deliverAnalystSubscriptions = () => requestOperation('deliverAnalystSubscriptions');
