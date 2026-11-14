package com.marketdeck.app;

import org.junit.Test;
import static org.junit.Assert.*;

public class ResourceHealthTest {
    @Test public void unrelatedSuccessDoesNotClearFailure(){
        ResourceHealth health=new ResourceHealth();
        health.succeeded("origin-a","summary",100);
        health.failed("origin-a","summary",200,"offline");
        health.succeeded("origin-a","chart",300);
        health.succeeded("origin-b","summary",300);
        assertFalse(health.get("origin-a","summary").fresh(300,1000));
        assertEquals("offline",health.get("origin-a","summary").error);
        assertTrue(health.get("origin-a","chart").fresh(300,1000));
        assertTrue(health.get("origin-b","summary").fresh(300,1000));
    }
    @Test public void staleUnknownAndFutureSuccessRemainUnavailable(){
        ResourceHealth health=new ResourceHealth();
        assertFalse(health.get("origin","missing").fresh(1000,100));
        health.succeeded("origin","path",500);
        assertFalse(health.get("origin","path").fresh(400,100));
        assertFalse(health.get("origin","path").fresh(1000,100));
        assertTrue(health.get("origin","path").fresh(550,100));
    }
    @Test public void diagnosticsEvictionAndAttemptNeverDeleteUserData(){
        ResourceHealth health=new ResourceHealth();
        for(int i=0;i<129;i++)health.succeeded("origin","resource"+i,100);
        assertEquals(0,health.get("origin","resource0").lastSuccessMs);
        health.attempted("origin","resource128",200);
        assertEquals(100,health.get("origin","resource128").lastSuccessMs);
        assertEquals(200,health.get("origin","resource128").lastAttemptMs);
        for(int i=0;i<4;i++)health.succeeded("other"+i,"summary",300);
        assertEquals(0,health.get("origin","resource128").lastSuccessMs);
    }
    @Test public void failureWithoutMessageStillInvalidatesAndErrorIsBounded(){
        ResourceHealth health=new ResourceHealth();
        health.succeeded("origin","path",100);
        health.failed("origin","path",200,null);
        assertFalse(health.get("origin","path").fresh(200,500));
        health.failed("origin","path",201,new String(new char[400]).replace('\0','x'));
        assertEquals(300,health.get("origin","path").error.length());
    }
}
