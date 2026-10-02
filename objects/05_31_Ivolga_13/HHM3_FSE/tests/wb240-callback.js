'use strict';
// Exact exported shape, not an approximation of a newer API.
// wirenboard/wb-rules v2.40.0, commit 5eb62b848129a5736b9a816d7d2ffe594643451b,
// wbrules/engine.go newTrackHandler: objx.New(map[string]any{
//     "topic": msg.Topic, "value": msg.Payload,
// }). MQTTMessage.Retained and QoS are NOT exported.
module.exports=function(topic,value){return {topic,value};};
