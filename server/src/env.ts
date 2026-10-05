export type Env = {
  ROOM: DurableObjectNamespace;
  REGISTRY: DurableObjectNamespace;
};

export const ROOM_CODE = /^[a-z0-9-]{1,32}$/;
