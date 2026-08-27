/**
 * 미국 증시 및 매크로 종합 대시보드 브리핑 스크립트 (6컬럼 세분화 & 실제 집계일자 파싱 버전)
 */
function sendMorningBriefingWithNews() {
  
  // 1. 기초 데이터 및 실제 집계일자 동적 수집
  var indicators = getFinancialIndicatorsFromOpenAPI();
  var cycleData = getOECDCycleValueFromCSV();
  var macro = getMacroIndicators();
  
  // 2. 6컬럼 데이터 구조화 (가중치, 집계일자, 지표명, 현재 값, 적정값, 상태)
  var indicatorList = [
    { weight: 20, date: macro.cpiDate, name: "소비자물가지수 (CPI YoY)", value: macro.cpi, target: "2.0% 부근", status: macro.cpiStatus, category: "통화 정책 및 물가" },
    { weight: 15, date: macro.retailDate, name: "핵심 소매판매 (MoM)", value: macro.retailSales, target: "+0.0% 이상", status: macro.retailStatus, category: "고용 및 소비 핵심" },
    { weight: 15, date: macro.joblessDate, name: "주간 신규 실업수당 청구건수", value: macro.joblessClaims, target: "250K 이하", status: macro.joblessStatus, category: "고용 및 소비 핵심" },
    { weight: 10, date: indicators.tnxDate, name: "미 10년물 국채금리", value: (indicators.tnx !== "[데이터 수집 실패]" ? indicators.tnx + "%" : "[데이터 수집 실패]"), target: "3.5% ~ 4.0%", status: indicators.tnxStatus, category: "시장 위험 및 금융" },
    { weight: 10, date: indicators.sp500Date, name: "S&P 500 지수", value: indicators.sp500, target: "120일선 상회", status: (indicators.trend120 === "상회" ? "🟢 상회" : indicators.trend120 === "하회" ? "🚨 하회" : "판단불가"), category: "시장 위험 및 금융" },
    { weight: 10, date: macro.highYieldDate, name: "하이일드 채권 스프레드", value: (macro.highYield !== "[데이터 수집 실패]" ? macro.highYield + "%" : "[데이터 수집 실패]"), target: "4.5% 이하", status: macro.highYieldStatus, category: "경기 순환 및 신용 리스크" },
    { weight: 10, date: macro.yieldSpreadDate, name: "장단기 금리차 (10Y - 2Y)", value: macro.yieldSpread, target: "0.0%p 이상", status: macro.yieldSpreadStatus, category: "통화 정책 및 물가" },
    { weight: 5, date: cycleData.date, name: "경기선행지수 순환변동치", value: cycleData.value, target: "100.0 이상", status: cycleData.status, category: "경기 순환 및 신용 리스크" },
    { weight: 3, date: indicators.vixDate, name: "VIX (공포지수)", value: indicators.vix, target: "20.0 이하", status: indicators.vixStatus, category: "시장 위험 및 금융" },
    { weight: 2, date: macro.dxyDate, name: "달러 인덱스 (DXY)", value: macro.dxy, target: "100.0 이하", status: macro.dxyStatus, category: "통화 정책 및 물가" }
  ];
  
  // 3. 가중치 높은 순서(내림차순)로 배열 정렬
  indicatorList.sort(function(a, b) {
    return b.weight - a.weight;
  });
  
  // 4. 시장 추세 종합 진단 알고리즘
  var trend = "신중/관망 ⚠️";
  var trendColor = "#e67e22";
  
  if (indicators.sp500 === "[데이터 수집 실패]" || cycleData.value === "[데이터 수집 실패]" || macro.highYield === "[데이터 수집 실패]") {
    trend = "종합 판단 불가 ❌ (핵심 데이터 수집 실패)";
    trendColor = "#7f8c8d";
  } else {
    var isMarketBull = (indicators.vix !== "[데이터 수집 실패]" && parseFloat(indicators.vix) < 18 && indicators.trend120 === "상회");
    var isCycleRising = (cycleData.status.indexOf("확장") !== -1 || cycleData.status.indexOf("회복") !== -1);
    var isCreditStable = (macro.highYield !== "[데이터 수집 실패]" && parseFloat(macro.highYield) < 4.5);

    if (isMarketBull && isCycleRising && isCreditStable) {
      trend = "적극 성장 국면 🚀 (시장·매크로·신용 위험 전방위 안정)";
      trendColor = "#27ae60";
    } else if (isMarketBull && !isCycleRising) {
      trend = "경계 및 비중 축소 🚨 (선행지수 꺾임 / 다이버전스 발생)";
      trendColor = "#d93025";
    } else if ((macro.highYield !== "[데이터 수집 실패]" && parseFloat(macro.highYield) >= 4.5) || macro.joblessStatus.indexOf("⚠️") !== -1) {
      trend = "경기 둔화 및 리스크 관리 국면 ⚠️ (신용위험 고조 또는 고용 둔화)";
      trendColor = "#c0392b";
    }
  }
  
  // 5. 구글 뉴스 RSS 가져오기
  var newsArticlesHtml = getUSMarketNewsHtml();
  
  // 6. 이메일 전송용 HTML 본문 조립 (6컬럼 테이블 세분화 적용)
  var today = Utilities.formatDate(new Date(), "GMT+9", "yyyy-MM-dd");
  var htmlBody = "<div style='font-family: Malgun Gothic, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 8px;'>" +
                 "<h2 style='color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px;'>📅 " + today + " 매크로 종합 정밀 브리핑</h2>" +
                 
                 "<div style='background: #f8f9fa; padding: 15px; border-left: 5px solid " + trendColor + "; border-radius: 4px; margin-bottom: 20px;'>" +
                 "<h4 style='margin: 0 0 5px 0; color: #555;'>💡 마스터 알고리즘 판정</h4>" +
                 "<p style='margin: 0; font-size: 16px; font-weight: bold; color: " + trendColor + ";'>" + trend + "</p>" +
                 "</div>" +
                 
                 "<h3>📊 6컬럼 매크로 매트릭스 (가중치 순 정렬)</h3>" +
                 "<table style='width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px;'>" +
                 "<thead>" +
                 "<tr style='background-color: #f1f3f4; border-bottom: 2px solid #ccc; text-align: left;'>" +
                 "<th style='padding: 10px; width: 8%; text-align:center;'>가중치</th>" +
                 "<th style='padding: 10px; width: 14%;'>집계일자</th>" +
                 "<th style='padding: 10px; width: 33%;'>지표명</th>" +
                 "<th style='padding: 10px; width: 15%;'>현재 값</th>" +
                 "<th style='padding: 10px; width: 15%;'>적정값</th>" +
                 "<th style='padding: 10px; width: 15%;'>상태</th>" +
                 "</tr>" +
                 "</thead>" +
                 "<tbody>";

  for (var i = 0; i < indicatorList.length; i++) {
    var item = indicatorList[i];
    htmlBody += "<tr style='border-bottom: 1px solid #eee;'>" +
                "<td style='padding: 10px; font-weight: bold; color: #e67e22; text-align:center;'>" + item.weight + "%</td>" +
                "<td style='padding: 10px; color: #666;'>" + item.date + "</td>" +
                "<td style='padding: 10px;'><b>" + item.name + "</b><br><span style='font-size: 11px; color: #888;'>" + item.category + "</span></td>" +
                "<td style='padding: 10px; font-weight: bold;'>" + item.value + "</td>" +
                "<td style='padding: 10px; color: #555;'>" + item.target + "</td>" +
                "<td style='padding: 10px;'>" + item.status + "</td>" +
                "</tr>";
  }

  htmlBody += "</tbody></table>" +
              "<hr style='border: 0; border-top: 1px solid #eee;'>" +
              
              "<h3>📰 전일 미증시 주요 뉴스</h3>" + 
              newsArticlesHtml +
              "</div>";
  
  // 7. 메일 발송
  var myEmail = Session.getActiveUser().getEmail();
  MailApp.sendEmail({
    to: myEmail,
    subject: "[매크로 대시보드] 6컬럼 정밀 브리핑 - " + today,
    htmlBody: htmlBody
  });
}

/**
 * FRED 미국 경기선행지수 순환변동치 파싱
 */
function getOECDCycleValueFromCSV() {
  var result = { value: "[데이터 수집 실패]", status: "판단불가", date: "-" };
  try {
    var url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=USALOLITOAASTSAM";
    var response = UrlFetchApp.fetch(url, { "muteHttpExceptions": true });
    if (response.getResponseCode() === 200) {
      var lines = response.getContentText().split("\n");
      var validRows = [];
      for (var i = 1; i < lines.length; i++) {
        var parts = lines[i].split(",");
        if (parts.length === 2 && parts[1].trim() !== "." && parts[1].trim() !== "") {
          validRows.push({ date: parts[0].trim(), value: parseFloat(parts[1].trim()) });
        }
      }
      if (validRows.length >= 2) {
        var latest = validRows[validRows.length - 1];
        var prev = validRows[validRows.length - 2];
        result.value = latest.value.toFixed(2);
        result.date = latest.date;
        
        if (latest.value > prev.value) {
          result.status = latest.value >= 100 ? "🟢 확장 국면" : "🟢 회복 전환";
        } else {
          result.status = latest.value >= 100 ? "🚨 하락 꺾임" : "📉 수축 국면";
        }
      }
    }
  } catch(e) { Logger.log("FRED 순환변동치 에러: " + e.toString()); }
  return result;
}

/**
 * 실시간 금융 지표 수집 및 거래일자(집계일) 추출
 */
function getFinancialIndicatorsFromOpenAPI() {
  var data = { 
    sp500: "[데이터 수집 실패]", sp500Date: "-", trend120: "판단불가", ma120: "-",
    vix: "[데이터 수집 실패]", vixDate: "-", vixStatus: "판단불가",
    tnx: "[데이터 수집 실패]", tnxDate: "-", tnxStatus: "판단불가" 
  };
  try {
    // 1. S&P 500
    var responseSp500 = UrlFetchApp.fetch("https://query2.finance.yahoo.com/v8/finance/chart/%5ESPX?interval=1d&numberOfPoints=150", { "muteHttpExceptions": true });
    var jsonSp500 = JSON.parse(responseSp500.getContentText());
    if (jsonSp500.chart.result && jsonSp500.chart.result[0]) {
      var result = jsonSp500.chart.result[0];
      var currentPrice = result.meta.regularMarketPrice;
      data.sp500 = currentPrice.toFixed(2);
      
      var timestamp = result.timestamp;
      if (timestamp && timestamp.length > 0) {
        data.sp500Date = Utilities.formatDate(new Date(timestamp[timestamp.length - 1] * 1000), "GMT-5", "yyyy-MM-dd");
      }
      
      var closePrices = result.indicators.quote[0].close || [];
      var validPrices = closePrices.filter(function(p) { return p !== null && p !== undefined && !isNaN(p); });
      if (validPrices.length >= 120) {
        var recent120 = validPrices.slice(-120);
        var sum = recent120.reduce(function(a, b) { return a + b; }, 0);
        var ma120Value = sum / 120;
        data.ma120 = ma120Value.toFixed(2);
        data.trend120 = currentPrice > ma120Value ? "상회" : "하회";
      }
    }
    
    // 2. VIX
    var responseVix = UrlFetchApp.fetch("https://query2.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=1d", { "muteHttpExceptions": true });
    var jsonVix = JSON.parse(responseVix.getContentText());
    if (jsonVix.chart.result && jsonVix.chart.result[0]) {
      var vixVal = jsonVix.chart.result[0].meta.regularMarketPrice;
      data.vix = vixVal.toFixed(2);
      data.vixStatus = vixVal >= 20 ? "⚠️ 위험 감지" : "🟢 안정권";
      var vTs = jsonVix.chart.result[0].timestamp;
      if(vTs) data.vixDate = Utilities.formatDate(new Date(vTs[vTs.length - 1] * 1000), "GMT-5", "yyyy-MM-dd");
    }

    // 3. TNX (10년물 금리)
    var responseTnx = UrlFetchApp.fetch("https://query2.finance.yahoo.com/v8/finance/chart/%5ETNX?interval=1d&range=1d", { "muteHttpExceptions": true });
    var jsonTnx = JSON.parse(responseTnx.getContentText());
    if (jsonTnx.chart.result && jsonTnx.chart.result[0]) {
      var tnxVal = jsonTnx.chart.result[0].meta.regularMarketPrice;
      data.tnx = tnxVal.toFixed(3);
      data.tnxStatus = (tnxVal >= 4.5 ? "⚠️ 고금리 부담" : "🟢 정상범위");
      var tTs = jsonTnx.chart.result[0].timestamp;
      if(tTs) data.tnxDate = Utilities.formatDate(new Date(tTs[tTs.length - 1] * 1000), "GMT-5", "yyyy-MM-dd");
    }
  } catch (e) { Logger.log(e.toString()); }
  return data;
}

/**
 * 매크로 지표 파싱 및 각 데이터 세부 집계일 추출
 */
function getMacroIndicators() {
  var macro = { 
    yieldSpread: "[데이터 수집 실패]", yieldSpreadDate: "-", yieldSpreadStatus: "판단불가",
    dxy: "[데이터 수집 실패]", dxyDate: "-", dxyStatus: "판단불가",
    cpi: "[데이터 수집 실패]", cpiDate: "-", cpiStatus: "판단불가",
    highYield: "[데이터 수집 실패]", highYieldDate: "-", highYieldStatus: "판단불가",
    joblessClaims: "[데이터 수집 실패]", joblessDate: "-", joblessStatus: "판단불가",
    retailSales: "[데이터 수집 실패]", retailDate: "-", retailStatus: "판단불가"
  };
  try {
    // 1. 달러 인덱스 (DXY)
    var responseDxy = UrlFetchApp.fetch("https://query2.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1d&range=1d", { "muteHttpExceptions": true });
    var jsonDxy = JSON.parse(responseDxy.getContentText());
    if (jsonDxy.chart.result && jsonDxy.chart.result[0]) {
      var dxyVal = jsonDxy.chart.result[0].meta.regularMarketPrice;
      macro.dxy = dxyVal.toFixed(2);
      macro.dxyStatus = dxyVal >= 105 ? "⚠️ 고달러" : "🟢 정상";
      var dTs = jsonDxy.chart.result[0].timestamp;
      if(dTs) macro.dxyDate = Utilities.formatDate(new Date(dTs[dTs.length - 1] * 1000), "GMT-5", "yyyy-MM-dd");
    }
    
    // 2. 장단기 금리차 (10Y - 2Y)
    var spreadResponse = UrlFetchApp.fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10Y2Y", { "muteHttpExceptions": true });
    if (spreadResponse.getResponseCode() === 200) {
      var sLines = spreadResponse.getContentText().split("\n");
      var sValid = [];
      for(var i=1; i<sLines.length; i++) {
        var p = sLines[i].split(",");
        if(p.length === 2 && p[1].trim() !== "." && p[1].trim() !== "") sValid.push({ date: p[0].trim(), val: parseFloat(p[1].trim()) });
      }
      if(sValid.length > 0) {
        var sLatest = sValid[sValid.length - 1];
        macro.yieldSpread = sLatest.val.toFixed(2) + "%p";
        macro.yieldSpreadDate = sLatest.date;
        macro.yieldSpreadStatus = sLatest.val < 0 ? "⚠️ 역전 상태" : "🟢 정상화 완료";
      }
    }
    
    // 3. 소비자물가지수 (CPI YoY)
    var cpiResponse = UrlFetchApp.fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL", { "muteHttpExceptions": true });
    if (cpiResponse.getResponseCode() === 200) {
      var cLines = cpiResponse.getContentText().split("\n");
      var cValid = [];
      for(var j=1; j<cLines.length; j++) {
        var cp = cLines[j].split(",");
        if(cp.length === 2 && cp[1].trim() !== "." && cp[1].trim() !== "") cValid.push({ date: cp[0].trim(), val: parseFloat(cp[1].trim()) });
      }
      if(cValid.length >= 13) {
        var curCpi = cValid[cValid.length - 1];
        var baseCpi = cValid[cValid.length - 13];
        macro.cpi = (((curCpi.val - baseCpi.val) / baseCpi.val) * 100).toFixed(1) + "%";
        macro.cpiDate = curCpi.date; // 예: 2026-05-01 (해당 월 집계일)
        macro.cpiStatus = parseFloat(macro.cpi) >= 3.0 ? "⚠️ 인플레 잔존" : "🟢 안정화";
      }
    }

    // 4. 하이일드 채권 스프레드
    var hyResponse = UrlFetchApp.fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2", { "muteHttpExceptions": true });
    if (hyResponse.getResponseCode() === 200) {
      var hyLines = hyResponse.getContentText().split("\n");
      var hyValid = [];
      for(var k=1; k<hyLines.length; k++) {
        var hyp = hyLines[k].split(",");
        if(hyp.length === 2 && hyp[1].trim() !== "." && hyp[1].trim() !== "") hyValid.push({ date: hyp[0].trim(), val: parseFloat(hyp[1].trim()) });
      }
      if(hyValid.length > 0) {
        var hyLatest = hyValid[hyValid.length - 1];
        macro.highYield = hyLatest.val.toFixed(2);
        macro.highYieldDate = hyLatest.date;
        macro.highYieldStatus = hyLatest.val >= 4.5 ? "⚠️ 위험 고조" : "🟢 리스크 낮음";
      }
    }

    // 5. 주간 신규 실업수당 청구건수
    var jcResponse = UrlFetchApp.fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=ICSA", { "muteHttpExceptions": true });
    if (jcResponse.getResponseCode() === 200) {
      var jcLines = jcResponse.getContentText().split("\n");
      var jcValid = [];
      for(var m=1; m<jcLines.length; m++) {
        var jcp = jcLines[m].split(",");
        if(jcp.length === 2 && jcp[1].trim() !== "." && jcp[1].trim() !== "") jcValid.push({ date: jcp[0].trim(), val: parseFloat(jcp[1].trim()) });
      }
      if(jcValid.length > 0) {
        var jcLatest = jcValid[jcValid.length - 1];
        macro.joblessClaims = (jcLatest.val / 1000).toFixed(0) + "K";
        macro.joblessDate = jcLatest.date; // 해당 주간 마감일
        macro.joblessStatus = jcLatest.val >= 250000 ? "⚠️ 고용 둔화" : "🟢 고용 견고";
      }
    }

    // 6. 핵심 소매판매 MoM
    var rsResponse = UrlFetchApp.fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=RSXFS", { "muteHttpExceptions": true });
    if (rsResponse.getResponseCode() === 200) {
      var rsLines = rsResponse.getContentText().split("\n");
      var rsValid = [];
      for(var n=1; n<rsLines.length; n++) {
        var rsp = rsLines[n].split(",");
        if(rsp.length === 2 && rsp[1].trim() !== "." && rsp[1].trim() !== "") rsValid.push({ date: rsp[0].trim(), val: parseFloat(rsp[1].trim()) });
      }
      if(rsValid.length >= 2) {
        var rsLatest = rsValid[rsValid.length - 1];
        var rsPrev = rsValid[rsValid.length - 2];
        var rsMoM = (((rsLatest.val - rsPrev.val) / rsPrev.val) * 100).toFixed(1);
        macro.retailSales = (rsMoM > 0 ? "+" + rsMoM : rsMoM) + "%";
        macro.retailDate = rsLatest.date;
        macro.retailStatus = rsMoM >= 0 ? "🟢 소비 확장" : "📉 소비 둔화";
      }
    }
    
  } catch(e) { Logger.log("매크로 세부 수집 에러: " + e.toString()); }
  return macro;
}

function getUSMarketNewsHtml() {
  var url = "https://news.google.com/rss/search?q=" + encodeURIComponent("뉴욕증시 OR 미국증시 OR 매크로경제") + "&hl=ko&gl=KR&ceid=KR:ko";
  try {
    var response = UrlFetchApp.fetch(url);
    var xml = response.getContentText();
    var document = XmlService.parse(xml);
    var root = document.getRootElement();
    var channel = root.getChild("channel");
    var items = channel.getChildren("item");
    var htmlString = "<ol style='padding-left: 20px;'>";
    for (var i = 0; i < Math.min(items.length, 3); i++) {
      var title = items[i].getChildText("title");
      var link = items[i].getChildText("link");
      htmlString += "<li style='margin-bottom: 10px;'><a href='" + link + "' target='_blank' style='color: #1a73e8; text-decoration: none; font-weight: bold;'> " + title.split(" - ")[0] + "</a></li>";
    }
    htmlString += "</ol>";
    return htmlString;
  } catch (e) { return "<p style='color: red;'>❌ 뉴스 로드 실패</p>"; }
}
