const int enPin=8;
const int stepXPin = 2; //X.STEP
const int dirXPin = 5; // X.DIR
const int stepYPin = 3; //Y.STEP
const int dirYPin = 6; // Y.DIR
const int stepZPin = 4; //Z.STEP
const int dirZPin = 7; // Z.DIR

int stepPin=stepXPin;
int dirPin=dirXPin;

const int stepsPerRev=200;
int pulseWidthMicros = 100;  // microseconds
int millisBtwnSteps = 1000;

void setup() {
  Serial.begin(9600);
  pinMode(enPin, OUTPUT);
  digitalWrite(enPin, LOW);
  pinMode(stepXPin, OUTPUT);
  pinMode(dirXPin, OUTPUT);
  pinMode(stepZPin, OUTPUT);
  pinMode(dirZPin, OUTPUT);
 
  Serial.println(F("CNC Shield Initialized"));
}

void loop() {
  Serial.println(F("Step 1"));
  makeMove(100,0);
  delay(500);
  Serial.println(F("Step 2"));
  makeMove(0,100);
  delay(500);
  Serial.println(F("Step 3"));
  makeMove(-100,0);
  delay(500);
  Serial.println(F("Step 4"));
  makeMove(0,-100);
  delay(5000);
}

void makeMove(double deltaX, double deltaY){

  double deltaA = deltaX + deltaY;
  double deltaB = deltaX - deltaY;


  int stepsA = abs(round(deltaA/0.212058));
  int stepsB = abs(round(deltaB/0.212058));

  
  if (deltaA >= 0){
    digitalWrite(dirXPin, HIGH);
  }
  else{
    digitalWrite(dirXPin, LOW);
  }
  if (deltaB >= 0){
    digitalWrite(dirZPin, HIGH);
  }
  else{
    digitalWrite(dirZPin, LOW);
  }
  for (int i = 0; i < stepsA; i++) {
    digitalWrite(stepXPin, HIGH);
    digitalWrite(stepZPin, HIGH);
    delayMicroseconds(pulseWidthMicros);
    digitalWrite(stepXPin, LOW);
    digitalWrite(stepZPin, LOW);
    delayMicroseconds(millisBtwnSteps);
  }
  
}
