-- For SQLite

CREATE TABLE INW_FileHeader (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    BankControlId   VARCHAR(4)      NOT NULL,
    FieldId         VARCHAR(3)      NOT NULL,
    FileDate        VARCHAR(5)      NOT NULL,
    BankCode        VARCHAR(4)      NOT NULL,
    NumBatches      VARCHAR(3)      NOT NULL,
    NumTransactions VARCHAR(6)      NOT NULL,
    Blank           VARCHAR(155)    NOT NULL,
    Status          INTEGER         NOT NULL DEFAULT 0,
    TimeUpdated     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FileName        VARCHAR(20)     NOT NULL
);

CREATE TABLE INW_BranchHeader (
    Id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    BranchControlId         VARCHAR(4)  NOT NULL,
    FieldId                 VARCHAR(3)  NOT NULL,
    FileDate                VARCHAR(5)  NOT NULL,
    BankCode                VARCHAR(4)  NOT NULL,
    BranchCode              VARCHAR(3)  NOT NULL,
    CreditTotal             VARCHAR(15) NOT NULL,
    NumCreditItems          VARCHAR(6)  NOT NULL,
    DebitTotal              VARCHAR(15) NOT NULL,
    NumDebitItems           VARCHAR(6)  NOT NULL,
    AccountHashTotal        VARCHAR(18) NOT NULL,
    Blank                   VARCHAR(101) NOT NULL,
    Status                  INTEGER     NOT NULL DEFAULT 0,
    TimeUpdated             DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FileName                VARCHAR(20) NOT NULL
);

CREATE TABLE INW_Transaction (
    Id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    Transaction_Id                  VARCHAR(4)  NOT NULL,
    Destination_Bank_No             VARCHAR(4)  NOT NULL,
    Destination_Branch_No           VARCHAR(3)  NOT NULL,
    Destination_Ac_No               VARCHAR(12) NOT NULL,
    Destination_Ac_Name             VARCHAR(20) NOT NULL,
    Transaction_Code                VARCHAR(2)  NOT NULL,
    Return_Code                     VARCHAR(2),
    Filler                          VARCHAR(1)  NOT NULL,
    Original_Transaction_Date       VARCHAR(6),
    Amount                          VARCHAR(12) NOT NULL,
    Currency_Code                   VARCHAR(3)  NOT NULL,
    Originating_Bank_No             VARCHAR(4)  NOT NULL,
    Originating_Branch_No           VARCHAR(3)  NOT NULL,
    Originating_Ac_No               VARCHAR(12) NOT NULL,
    Originating_Ac_Name             VARCHAR(20) NOT NULL,
    Particular                      VARCHAR(15),
    Reference                       VARCHAR(15),
    Value_Date                      VARCHAR(6)  NOT NULL,
    Security_Check_Field            VARCHAR(6),
    Blank                           VARCHAR(30) NOT NULL,
    TimeUpdated                     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FileName                        VARCHAR(20) NOT NULL,
    AmountInt                       INTEGER
);

-- OUTWARD TRANSACTIONS
CREATE TABLE OUT_FileHeader (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    BankControlId   VARCHAR(4)      NOT NULL,
    FieldId         VARCHAR(3)      NOT NULL,
    FileDate        VARCHAR(5)      NOT NULL,
    BankCode        VARCHAR(4)      NOT NULL,
    NumBatches      VARCHAR(3)      NOT NULL,
    NumTransactions VARCHAR(6)      NOT NULL,
    Blank           VARCHAR(155)    NOT NULL,
    Status          INTEGER         NOT NULL DEFAULT 0,
    TimeUpdated     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FileName        VARCHAR(20)     NOT NULL
);

CREATE TABLE OUT_BranchHeader (
    Id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    BranchControlId         VARCHAR(4)  NOT NULL,
    FieldId                 VARCHAR(3)  NOT NULL,
    FileDate                VARCHAR(5)  NOT NULL,
    BankCode                VARCHAR(4)  NOT NULL,
    BranchCode              VARCHAR(3)  NOT NULL,
    CreditTotal             VARCHAR(15) NOT NULL,
    NumCreditItems          VARCHAR(6)  NOT NULL,
    DebitTotal              VARCHAR(15) NOT NULL,
    NumDebitItems           VARCHAR(6)  NOT NULL,
    AccountHashTotal        VARCHAR(18) NOT NULL,
    Blank                   VARCHAR(101) NOT NULL,
    Status                  INTEGER     NOT NULL DEFAULT 0,
    TimeUpdated             DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FileName                VARCHAR(20) NOT NULL
);

CREATE TABLE OUT_Transaction (
    Id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    Transaction_Id                  VARCHAR(4)  NOT NULL,
    Destination_Bank_No             VARCHAR(4)  NOT NULL,
    Destination_Branch_No           VARCHAR(3)  NOT NULL,
    Destination_Ac_No               VARCHAR(12) NOT NULL,
    Destination_Ac_Name             VARCHAR(20) NOT NULL,
    Transaction_Code                VARCHAR(2)  NOT NULL,
    Return_Code                     VARCHAR(2),
    Filler                          VARCHAR(1)  NOT NULL,
    Original_Transaction_Date       VARCHAR(6),
    Amount                          VARCHAR(12) NOT NULL,
    Currency_Code                   VARCHAR(3)  NOT NULL,
    Originating_Bank_No             VARCHAR(4)  NOT NULL,
    Originating_Branch_No           VARCHAR(3)  NOT NULL,
    Originating_Ac_No               VARCHAR(12) NOT NULL,
    Originating_Ac_Name             VARCHAR(20) NOT NULL,
    Particular                      VARCHAR(15),
    Reference                       VARCHAR(15),
    Value_Date                      VARCHAR(6)  NOT NULL,
    Security_Check_Field            VARCHAR(6),
    Blank                           VARCHAR(30) NOT NULL,
    TimeUpdated                     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FileName                        VARCHAR(20) NOT NULL,
    AmountInt                       INTEGER
);